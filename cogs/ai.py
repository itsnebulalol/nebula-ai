import asyncio
from datetime import datetime
from io import BytesIO
from json import dumps
from random import choice
from tempfile import NamedTemporaryFile
from time import time
from traceback import format_exc
from typing import List

import asyncssh
import discord
import whisper
from aiohttp import ClientSession
from aiohttp_socks import ProxyConnector
from discord import (
    ButtonStyle,
    Color,
    Embed,
    Interaction,
    SelectOption,
    app_commands,
    ui,
)
from discord.ext import commands
from discord.ext.commands import Context
from openai import AsyncOpenAI

from plugins import (
    ImageGenPlugin,
    ImagesPlugin,
    RedditPlugin,
    ShellPlugin,
    TwitterPlugin,
    WebPlugin,
    YouTubePlugin,
)
from utils.colorthief import get_color
from utils.container import PythonContainer
from utils.context_commands import add_context_commands
from utils.jsons import AIConfigJSON, ConfigJSON


class CodeSelectMenu(ui.Select):
    def __init__(self, scripts, connection):
        options = [
            SelectOption(label=f"Script {i+1}", value=str(i))
            for i in range(len(scripts))
        ]
        super().__init__(placeholder="Select a script to run", options=options)
        self.scripts = scripts
        self.connection = connection

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        selected_index = int(self.values[0])
        selected_script = self.scripts[selected_index]

        loading_embed = discord.Embed(
            description="<a:loading:1292980861142040606> Starting container...",
            color=discord.Color.blue(),
        )
        loading_message = await interaction.followup.send(embed=loading_embed)

        try:
            container = PythonContainer(self.connection)
            container_id = await container.start_container()

            try:
                loading_embed.description = (
                    "<a:loading:1292980861142040606> Writing script to container..."
                )
                await loading_message.edit(embed=loading_embed)
                await container.write_file_in_container(container_id, selected_script)

                loading_embed.description = f"<a:loading:1292980861142040606> Running script {selected_index + 1}..."
                await loading_message.edit(embed=loading_embed)
                result = await container.run_python_file(container_id)

                embed = discord.Embed(
                    title=f"Script {selected_index + 1} Output",
                    color=(
                        discord.Color.green()
                        if result["exit_code"] == 0
                        else discord.Color.red()
                    ),
                    timestamp=datetime.now(),
                )
                embed.add_field(
                    name="Exit Code", value=result["exit_code"], inline=False
                )

                output = result["output"] + result["error"]
                if len(output) > 4096:
                    file = discord.File(BytesIO(output.encode()), filename="output.txt")
                    await loading_message.edit(embed=embed, attachments=[file])
                else:
                    embed.description = f"```\n{output}\n```"
                    await loading_message.edit(embed=embed)

            finally:
                await container.force_stop_container(container_id)

        except Exception as e:
            embed = discord.Embed(
                title="Error",
                description=f"An error occurred while running the script: {str(e)}",
                color=discord.Color.red(),
            )
            await loading_message.edit(embed=embed)


class RunCodeButton(ui.Button):
    def __init__(self, scripts, connection):
        super().__init__(style=ButtonStyle.green, label="Run Code", emoji="▶️")
        self.scripts = scripts
        self.connection = connection

    async def callback(self, interaction: discord.Interaction):
        embed = discord.Embed(title="Select a Script", color=discord.Color.blue())
        for i, script in enumerate(self.scripts):
            embed.add_field(
                name=f"Script {i+1}",
                value=f"```python\n{script[:100]}...```",
                inline=False,
            )

        view = ui.View()
        view.add_item(CodeSelectMenu(self.scripts, self.connection))
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class AI(commands.Cog, name="ai"):
    def __init__(self, bot) -> None:
        self.bot = bot
        self.bot.allowed_mentions = discord.AllowedMentions.none()

        self.config = ConfigJSON().load_json()
        self.ai_config = AIConfigJSON().load_json()

        self.proxies = self.load_proxies()

        self.client = AsyncOpenAI(base_url=self.ai_config["base_url"], api_key="ollama")
        self.session = ClientSession()
        if self.proxies == []:
            self.session_proxied = self.session
        else:
            self.session_proxied = ClientSession(
                connector=ProxyConnector.from_url(choice(self.proxies))
            )
        self.context = {}
        self.whisper_model = whisper.load_model("base")
        self.ssh_connection = None

        self.blacklist_ids = self.ai_config["blacklist"]
        self.system_prompt = [
            {
                "role": "system",
                "content": self.ai_config["system_prompt"].replace(
                    "{date}", datetime.utcnow().strftime("%Y-%m-%d")
                ),
            }
        ]
        self.owner_only_mode = False

        self.plugins = [
            ImagesPlugin(self.session),
            RedditPlugin(
                self.config["reddit"]["id"], self.config["reddit"]["secret"], "NebulaAI"
            ),
            YouTubePlugin(self.session, self.whisper_model),
            ImageGenPlugin(self.session, self.client, self.ai_config),
            ShellPlugin(self.session, self.client, self.ai_config),
            WebPlugin(self.session_proxied, self.client, self.ai_config, self.proxies),
        ]

        add_context_commands(self.bot, self.client, self.ai_config)

    async def cog_unload(self):
        for plugin in self.plugins:
            await plugin.plugin_unload()

        await self.session.close()
        await self.session_proxied.close()

        if self.ssh_connection:
            self.ssh_connection.close()

    def load_proxies(self):
        try:
            with open("config/proxies.txt", "r") as f:
                return [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            self.bot.logger.warn(
                "proxies.txt not found. DuckDuckGo requests and web scraping will be done without a proxy."
            )
            return []

    def increment_requests(self):
        self.ai_config["total_requests"] = self.ai_config["total_requests"] + 1
        AIConfigJSON().write_json(self.ai_config)

    async def handle_gpt(self, message: discord.Message):
        content = message.content.lstrip(";")
        loading_emoji = "<a:loading:1292980861142040606>"
        await message.add_reaction(loading_emoji)

        try:
            initial_message = None
            used_plugin = None
            user_context = self.context.get(message.author.id, [])
            try:
                recent_context = user_context[-4:]
            except:
                recent_context = user_context

            embed = Embed(
                description="<a:loading:1292980861142040606> AI is typing a response...",
                color=Color.blue(),
            )
            initial_message = await message.reply(embed=embed)

            for plugin in self.plugins:
                plugin_result = await plugin.process(
                    initial_message, message, content, recent_context
                )
                if plugin_result:
                    if plugin.normal_takeover:
                        self.increment_requests()

                        try:
                            await message.remove_reaction(loading_emoji, self.bot.user)
                        except:
                            pass

                        return
                    else:
                        try:
                            prompt, confidence = plugin_result
                        except:
                            prompt = plugin_result
                            confidence = None

                        used_plugin = plugin

                        break
            else:
                prompt = [
                    {"role": "user", "content": [{"type": "text", "text": content}]},
                ]
                confidence = None

            if message.author.id in self.context:
                full_prompt = (
                    self.system_prompt + self.context[message.author.id] + prompt
                )
            else:
                full_prompt = self.system_prompt + prompt

            model = (
                self.ai_config["models"]["vision"]
                if message.attachments
                else self.ai_config["models"]["text"]
            )

            before_time = time()
            completion = await self.client.chat.completions.create(
                model=model,
                messages=full_prompt,
            )
            processed_time = round(time() - before_time, 3)
            token_amount = completion.usage.completion_tokens
            tps = round(token_amount / processed_time, 1)
            tps_string = (
                f"time {processed_time}s, {token_amount} tokens, {tps} tokens/s"
            )

            response = completion.choices[0].message.content

            if message.author.id in self.context:
                self.context[message.author.id].append(prompt[0])
            else:
                self.context[message.author.id] = prompt

            self.context[message.author.id].append(
                {"role": "assistant", "content": response}
            )

            _, messages, _ = await self.send_response(
                message, response, tps_string, initial_message, used_plugin, confidence
            )
            self.increment_requests()

            try:
                await message.remove_reaction(loading_emoji, self.bot.user)
            except:
                pass

            return response, messages, tps_string
        except Exception as e:
            print(format_exc())

            embed = Embed(description=str(e), color=Color.red())
            if initial_message:
                await initial_message.edit(embed=embed)
            else:
                await message.reply(embed=embed)

            await message.remove_reaction(loading_emoji, self.bot.user)

            return None, None, None

    async def send_response(
        self,
        message,
        response,
        tps_string: str,
        initial_message=None,
        used_plugin=None,
        confidence: float = None,
    ):
        messages = []
        code_blocks = []

        parts = response.split("```")
        for i in range(1, len(parts), 2):
            if parts[i].startswith("python"):
                code_blocks.append(parts[i][6:].strip())

        for i in range(0, len(response), 2000):
            chunk = response[i : i + 2000]
            if messages:
                msg = await messages[-1].reply(chunk)
            elif initial_message:
                await initial_message.edit(content=chunk, embed=None)
                msg = initial_message
            else:
                try:
                    msg = await message.reply(chunk)
                except discord.errors.HTTPException:
                    embed = Embed(
                        description=f'{message.author.mention} deleted "**{message.content.lstrip(";")}**"',
                        color=Color.red(),
                    )
                    msg = await message.channel.send(chunk, embed=embed)
            messages.append(msg)

        plugin_info = (
            f"Used plugin: {used_plugin.name}{f' ({confidence} confidence) ' if confidence else ''}\n\n"
            if used_plugin
            else ""
        )
        embed = Embed(
            description=f"{plugin_info}{tps_string}",
            color=await get_color(message.author.avatar.url),
            timestamp=datetime.now(),
        )
        embed.set_footer(
            text=f"Request from {message.author.name}",
            icon_url=message.author.avatar.url,
        )

        if code_blocks:
            view = ui.View()
            connection = await self.get_ssh_connection()
            view.add_item(RunCodeButton(code_blocks, connection))
            await messages[-1].edit(embed=embed, view=view)
        else:
            await messages[-1].edit(embed=embed)

        return response, messages, tps_string

    async def get_ssh_connection(self):
        if not self.ssh_connection or self.ssh_connection.is_closed():
            private_key = asyncssh.read_private_key("config/docker.pem")
            self.ssh_connection = await asyncssh.connect(
                self.ai_config["container_host"]["ip"],
                username=self.ai_config["container_host"]["username"],
                client_keys=[private_key],
            )
        return self.ssh_connection

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        if message.author.id in self.blacklist_ids:
            return

        if self.owner_only_mode and not await self.bot.is_owner(message.author):
            return

        if message.attachments:
            if message.attachments[0].filename == "voice-message.ogg":
                with NamedTemporaryFile() as temp:
                    resp = await self.session.get(message.attachments[0].url)
                    temp.write(await resp.read())

                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(
                        None, lambda: self.whisper_model.transcribe(temp.name)
                    )

                    if result["text"] == "":
                        return

                    embed = discord.Embed(
                        title="Transcribed Text",
                        description=result["text"].lstrip(" "),
                        color=await get_color(message.author.avatar.url),
                    )
                    embed.set_footer(
                        text=f"Voice message from {message.author.name}",
                        icon_url=message.author.avatar.url,
                    )
                    embed.timestamp = datetime.now()

                    if message.channel.id == self.config["gpt_channel"]:
                        async with message.channel.typing():
                            _, msgs, tps = await self.handle_gpt(message)

                            embed.add_field(
                                name="AI Statistics", value=tps, inline=False
                            )

                            await msgs[-1].edit(embed=embed)
                    else:
                        await message.reply(embed=embed)

                    self.increment_requests()

                    return

        if message.channel.id != self.config[
            "gpt_channel"
        ] or not message.content.startswith(";"):
            return

        async with message.channel.typing():
            await self.handle_gpt(message)

    @commands.hybrid_command(description="Convert units")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @commands.cooldown(1, 10, commands.BucketType.user)
    @app_commands.describe(units="Units to convert (ex. '1 mi to ft')")
    async def convert(self, context: Context, units: str):
        await context.defer()

        if context.author.id in self.blacklist_ids:
            embed = discord.Embed(
                description="You are blacklisted from the AI features of this bot.",
                color=discord.Color.red(),
            )
            await context.send(embed=embed)
            return

        if self.owner_only_mode and not await self.bot.is_owner(context.author):
            embed = discord.Embed(
                description="This bot is in owner only mode.",
                color=discord.Color.red(),
            )
            await context.send(embed=embed)
            return

        try:
            prompt = [
                {"role": "user", "content": [{"type": "text", "text": units}]},
            ]

            with open("config/prompts/_general/convert.md", "r") as f:
                system_prompt = [
                    {
                        "role": "system",
                        "content": f.read().strip(),
                    }
                ]
                full_prompt = system_prompt + prompt

            completion = await self.client.chat.completions.create(
                model=self.ai_config["models"]["text"],
                messages=full_prompt,
            )

            response = completion.choices[0].message.content

            self.increment_requests()

            embed = Embed(
                title="Result",
                description=f"{units}\n\n=\n\n{response}",
                color=await get_color(context.author.avatar.url),
                timestamp=datetime.now(),
            )
            embed.set_footer(
                text=f"Request from {context.author.name}",
                icon_url=context.author.avatar.url,
            )
            await context.send(embed=embed)
        except Exception as e:
            print(format_exc())

            embed = Embed(description=str(e), color=Color.red())
            await context.send(embed=embed)

    @commands.hybrid_group(
        name="ai", description="Reset your context", fallback="reset"
    )
    async def ai(self, context: Context):
        if context.author.id not in self.context:
            embed = discord.Embed(
                description="You don't have a context stored.",
                color=discord.Color.red(),
            )
            await context.send(embed=embed)
        else:
            del self.context[context.author.id]
            embed = discord.Embed(
                description="Cleared your stored context.", color=discord.Color.green()
            )
            await context.send(embed=embed)

    @commands.is_owner()
    @ai.command(description="Reset everyone's context")
    async def resetall(self, context: Context):
        self.context.clear()
        embed = discord.Embed(
            description="Cleared everyone's stored context.",
            color=discord.Color.green(),
        )
        await context.send(embed=embed)

    @ai.command(description="Get the current system prompt")
    async def get_prompt(self, context: Context):
        prompt = self.system_prompt[0]["content"]
        await context.send(prompt)

    @commands.is_owner()
    @ai.command(description="Set the system prompt")
    @app_commands.describe(prompt="Text to set the system prompt to")
    async def set_prompt(self, context: Context, prompt: str):
        old_prompt = self.system_prompt[0]["content"]
        self.system_prompt[0]["content"] = prompt
        self.ai_config["system_prompt"] = prompt
        AIConfigJSON().write_json(self.ai_config)

        self.context.clear()

        embed = discord.Embed(
            description="Updated the system prompt and cleared everyone's stored context.",
            color=discord.Color.green(),
        )
        embed.add_field(name="Before", value=old_prompt, inline=False)
        embed.add_field(name="After", value=prompt, inline=False)

        await context.send(embed=embed)

    @ai.command(description="Get the current model")
    async def get_model(self, context: Context):
        embed = discord.Embed(
            title="Current Model",
            color=discord.Color.green(),
        )
        embed.add_field(
            name="Text", value=self.ai_config["models"]["text"], inline=False
        )
        embed.add_field(
            name="Vision", value=self.ai_config["models"]["vision"], inline=False
        )

        await context.send(embed=embed)

    async def models_autocompletion(
        self, interaction: Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        models = []
        tags = await self.session.get(
            f"{str(self.client.base_url).replace('v1/', '')}api/tags"
        )
        j = await tags.json()
        for model in j["models"]:
            models.append(model["name"])

        return [
            app_commands.Choice(name=choice, value=choice)
            for choice in models
            if current.lower() in choice.lower()
        ]

    @commands.is_owner()
    @ai.command(description="Set the model")
    @app_commands.describe(text_model="Model to set for text")
    @app_commands.autocomplete(text_model=models_autocompletion)
    @app_commands.describe(vision_model="Model to set for vision")
    @app_commands.autocomplete(vision_model=models_autocompletion)
    async def set_model(self, context: Context, text_model: str, vision_model: str):
        old_text = self.ai_config["models"]["text"]
        old_vision = self.ai_config["models"]["vision"]

        self.ai_config["models"]["text"] = text_model
        self.ai_config["models"]["vision"] = vision_model
        AIConfigJSON().write_json(self.ai_config)

        embed = discord.Embed(
            title="Updated Models",
            color=discord.Color.green(),
        )
        embed.add_field(
            name="Before", value=f"Text: {old_text}\nVision: {old_vision}", inline=False
        )
        embed.add_field(
            name="After",
            value=f"Text: {text_model}\nVision: {vision_model}",
            inline=False,
        )

        await context.send(embed=embed)

    @commands.is_owner()
    @ai.command(description="Get the current ollama base URL")
    async def get_base_url(self, context: Context):
        await context.send(str(self.client.base_url), ephemeral=True)

    @commands.is_owner()
    @ai.command(description="Set the ollama base URL")
    @app_commands.describe(url="New ollama base URL (ending with v1/)")
    async def set_base_url(self, context: Context, url: str):
        old_url = str(self.client.base_url)
        self.ai_config["base_url"] = url
        AIConfigJSON().write_json(self.ai_config)
        self.client.base_url = url

        embed = discord.Embed(
            title="Base URL change",
            color=discord.Color.green(),
        )
        embed.add_field(name="Before", value=old_url, inline=False)
        embed.add_field(name="After", value=url, inline=False)

        await context.send(embed=embed, ephemeral=True)

    @commands.is_owner()
    @ai.command(description="Blacklist a user from AI features")
    @app_commands.describe(user="User to blacklist")
    async def blacklist(self, context: Context, user: discord.Member):
        if user.id in self.blacklist_ids:
            embed = discord.Embed(
                description=f"{user.mention} ({user.id}) is already in the AI blacklist",
                color=discord.Color.red(),
            )
            await context.send(embed=embed)
            return

        self.blacklist_ids.append(user.id)
        AIConfigJSON().write_json(self.ai_config)

        embed = discord.Embed(
            title="Blacklist updated",
            description=f"Added {user.mention} ({user.id}) to AI blacklist",
            color=discord.Color.green(),
        )

        await context.send(embed=embed)

    @commands.is_owner()
    @ai.command(description="Unblacklist a user from AI features")
    @app_commands.describe(user="User to unblacklist")
    async def unblacklist(self, context: Context, user: discord.Member):
        if user.id not in self.blacklist_ids:
            embed = discord.Embed(
                description=f"{user.mention} ({user.id}) is not in the AI blacklist",
                color=discord.Color.red(),
            )
            await context.send(embed=embed)
            return

        self.ai_config["blacklist"].remove(user.id)
        AIConfigJSON().write_json(self.ai_config)
        self.blacklist_ids.remove(user.id)

        embed = discord.Embed(
            title="Blacklist updated",
            description=f"Removed {user.mention} ({user.id}) from AI blacklist",
            color=discord.Color.green(),
        )

        await context.send(embed=embed)

    @ai.command(description="Get the AI context of a user (defaults to author)")
    @app_commands.describe(user="User to get context of")
    async def get_context(self, context: Context, user: discord.Member = None):
        target_user = user or context.author
        if user is not None and not await self.bot.is_owner(context.author):
            if user.id != context.author.id:
                embed = discord.Embed(
                    description="You may only export your own context.",
                    color=discord.Color.red(),
                )
                await context.send(embed=embed)
                return

        try:
            user_context = self.context[target_user.id].copy()

            for message in user_context:
                if isinstance(message.get("content"), list):
                    for content in message["content"]:
                        if isinstance(content, dict) and "image_url" in content:
                            if "url" in content["image_url"] and content["image_url"][
                                "url"
                            ].startswith("data:image"):
                                content["image_url"][
                                    "url"
                                ] = "[BASE64_IMAGE_PLACEHOLDER]"

            text = dumps(user_context, indent=2).encode()
            await context.send(
                file=discord.File(
                    BytesIO(text), filename=f"{target_user.id}_context.txt"
                )
            )
        except KeyError:
            embed = discord.Embed(
                description=f"No context found for {target_user.mention}.",
                color=discord.Color.red(),
            )
            await context.send(embed=embed)
        except Exception as e:
            embed = discord.Embed(
                description=f"An error occurred while trying to get the user's context.\n\n{e}",
                color=discord.Color.red(),
            )
            await context.send(embed=embed)

    @commands.is_owner()
    @ai.command(description="Docker testing")
    async def docker(self, context: Context):
        await context.defer()
        try:
            private_key = asyncssh.read_private_key("config/docker.pem")
            async with asyncssh.connect(
                self.ai_config["container_host"]["ip"],
                username=self.ai_config["container_host"]["username"],
                client_keys=[private_key],
            ) as conn:
                cmd = "docker run --rm ai-alpine ping -c 4 1.1.1.1"
                result = await conn.run(cmd)

                if result.exit_status == 0:
                    output = result.stdout.strip()
                    if output:
                        await context.send(f"```\n{output}\n```")
                    else:
                        await context.send(
                            "Command executed successfully, but no output was returned."
                        )
                else:
                    await context.send(
                        f"Error executing command: {result.stderr.strip()}"
                    )
        except asyncssh.Error as e:
            await context.send(f"SSH connection failed: {str(e)}")
        except Exception as e:
            await context.send(f"An unexpected error occurred: {str(e)}")

    @commands.is_owner()
    @ai.command(description="Toggle owner-only mode")
    async def toggle_owner_only(self, context: Context):
        self.owner_only_mode = not self.owner_only_mode
        status = "enabled" if self.owner_only_mode else "disabled"
        embed = discord.Embed(
            description=f"Owner-only mode has been {status}.",
            color=discord.Color.green(),
        )
        await context.send(embed=embed)


async def setup(bot) -> None:
    await bot.add_cog(AI(bot))

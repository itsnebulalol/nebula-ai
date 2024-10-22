from datetime import datetime
from io import BytesIO
from re import search
from time import time

import discord
from aiohttp import ClientSession
from asyncssh import Error as AsyncSSHError
from asyncssh import connect, read_private_key
from openai import AsyncOpenAI

from utils.colorthief import get_color
from utils.container import SSHContainer

from ._plugin import AIPlugin


class ShellPlugin(AIPlugin):
    name = "Shell"
    normal_takeover = True

    def __init__(self, session: ClientSession, client: AsyncOpenAI, ai_config):
        self.session = session
        self.client = client
        self.ai_config = ai_config

        super().__init__()

    async def process(
        self,
        initial_message,
        message,
        content,
        context,
    ):
        should_use, confidence = await self.should_use_plugin(content)
        if should_use:
            await self.update_embed(initial_message, "Generating commands...")
            gen_before_time = time()
            commands = await self.generate_commands(content)
            gen_processed_time = round(time() - gen_before_time, 3)

            try:
                private_key = read_private_key("config/docker.pem")

                before_time = time()
                async with connect(
                    self.ai_config["container_host"]["ip"],
                    username=self.ai_config["container_host"]["username"],
                    client_keys=[private_key],
                ) as conn:
                    container = SSHContainer(conn)

                    await self.update_embed(initial_message, "Starting container...")
                    container_id = await container.start_container()

                    await self.update_embed(initial_message, "Running commands...")
                    results = []
                    for cmd in (
                        commands.replace("```bash", "```")
                        .replace("```shell", "```")
                        .split("```")[1:]
                    ):
                        print(cmd)
                        cmd = cmd.strip().split("```")[0].strip()
                        if cmd:
                            result = await container.exec_in_container(
                                container_id, cmd
                            )
                            results.append(result)

                    await container.force_stop_container(container_id)

                    processed_time = round(time() - before_time, 3)

                    out = ""
                    for result in results:
                        out += f"$ {result['command']}\n"
                        out += f"{result['output']}{result['error']}\n"

                    plugin_info = f"Used plugin: {self.name}{f' ({confidence} confidence) ' if confidence else ''}\n\n"
                    embed = discord.Embed(
                        description=f"{plugin_info}gen {gen_processed_time}s, exec {processed_time}s",
                        color=await get_color(message.author.avatar.url),
                        timestamp=datetime.now(),
                    )
                    embed.set_footer(
                        text=f"Request from {message.author.name}",
                        icon_url=message.author.avatar.url,
                    )

                    await self.send_split_message(initial_message, out, embed)
            except AsyncSSHError as e:
                await self.update_embed(
                    initial_message, f"SSH connection failed: {str(e)}", error=True
                )
            except Exception as e:
                await self.update_embed(
                    initial_message,
                    f"An unexpected error occurred: {str(e)}",
                    error=True,
                )

            return True

        return None

    async def should_use_plugin(self, content: str):
        prompt = [
            {
                "role": "system",
                "content": self.get_prompt("check"),
            },
            {
                "role": "user",
                "content": f"Determine the confidence level if the AI should use the plugin based on this input and the guidelines given to you: '{content}'\n\nRemember, provide only a number between 0.00 and 1.00, representing your confidence level. Do not write any other text. If you cannot do it, provide 0.00 to save time and resources.",
            },
        ]

        completion = await self.client.chat.completions.create(
            model=self.ai_config["models"]["text"],
            messages=prompt,
        )
        result = completion.choices[0].message.content.strip()
        print(result)

        fl = search(r"\d+\.\d+", result)
        if fl is None:
            return False, 0.00

        res = float(fl.group(0))

        try:
            if res >= 0.60:
                return True, res
            else:
                return False, res
        except:
            return False, 0.00

    async def generate_commands(self, content: str):
        prompt = [
            {
                "role": "system",
                "content": self.get_prompt("generate"),
            },
            {
                "role": "user",
                "content": f"Generate appropriate Linux shell commands based on this input: '{content}'\nProvide each command in its own code block. Remember, this is already running inside a container. Do not write any other text, comments, or stdout echos.",
            },
        ]

        completion = await self.client.chat.completions.create(
            model=self.ai_config["models"]["text"],
            messages=prompt,
        )
        generated_commands = completion.choices[0].message.content.strip()
        print(generated_commands)

        return generated_commands

    async def send_split_message(self, initial_message, content, embed):
        if len(content) > 1990:
            file = discord.File(BytesIO(content.encode()), filename="output.txt")

            await initial_message.edit(
                content="Your shell output was too long and has been written to a text file.",
                attachments=[file],
                embed=embed,
            )

            return [initial_message]
        else:
            formatted_content = f"```bash\n{content}\n```"
            await initial_message.edit(content=formatted_content, embed=embed)

            return [initial_message]

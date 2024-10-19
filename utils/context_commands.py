from datetime import datetime

import discord
from discord.ext import commands
from openai import AsyncOpenAI

from utils.colorthief import get_color
from utils.jsons import AIConfigJSON


def add_context_commands(bot: commands.Bot, client: AsyncOpenAI, ai_config):
    @discord.app_commands.allowed_installs(guilds=True, users=True)
    @discord.app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @commands.cooldown(1, 10, commands.BucketType.user)
    @bot.tree.context_menu(name="Summarize message")
    async def summarize_msg(interaction: discord.Interaction, message: discord.Message):
        await interaction.response.defer(ephemeral=True)

        if interaction.user.id in ai_config["blacklist"]:
            embed = discord.Embed(
                description="You are blacklisted from the AI features of this bot.",
                color=discord.Color.red(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        try:
            prompt = [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": message.content}],
                },
            ]

            with open("config/prompts/_general/summary.md", "r") as f:
                system_prompt = [
                    {
                        "role": "system",
                        "content": f.read().strip(),
                    }
                ]
            full_prompt = system_prompt + prompt

            completion = await client.chat.completions.create(
                model=ai_config["models"]["text"],
                messages=full_prompt,
            )
            response = completion.choices[0].message.content

            ai_config["total_requests"] = ai_config["total_requests"] + 1
            AIConfigJSON().write_json(ai_config)

            embed = discord.Embed(
                title="Message Summary",
                description=f"{response}",
                color=await get_color(interaction.user.avatar.url),
                timestamp=datetime.now(),
            )
            embed.set_footer(
                text=f"Request from {interaction.user.name}",
                icon_url=interaction.user.avatar.url,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            embed = discord.Embed(description=str(e), color=discord.Color.red())
            await interaction.followup.send(embed=embed, ephemeral=True)

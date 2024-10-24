from abc import ABC, abstractmethod
from datetime import datetime
from os import listdir, path

import discord


class AIPlugin(ABC):
    name = "Plugin"
    normal_takeover = False

    def __init__(self):
        self.prompts = self.load_prompts()
        print(
            f"\x1b[30m\x1b[1m{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\x1b[0m \x1b[34m\x1b[1mINFO    \x1b[0m \x1b[32m\x1b[1mNebulaAI\x1b[0m Loaded AI plugin '{self.name}'"
        )

    async def plugin_load(self):
        # TODO: make this work
        pass

    async def plugin_unload(self):
        pass

    def load_prompts(self) -> dict:
        prompts = {}
        plugin_file_name = str(self.__class__).split(".")[1]
        prompt_dir = f"config/prompts/{plugin_file_name}"
        if path.exists(prompt_dir):
            for filename in listdir(prompt_dir):
                if filename.endswith(".md"):
                    prompt_name = path.splitext(filename)[0]
                    with open(path.join(prompt_dir, filename), "r") as file:
                        prompts[prompt_name] = file.read().strip()

        return prompts

    def get_prompt(self, prompt_name) -> str:
        return self.prompts.get(prompt_name, "")

    @abstractmethod
    async def process(
        self,
        initial_message: discord.Message,
        message: discord.Message,
        content: str,
        context: list,
    ):
        pass

    async def send_initial_embed(self, message: discord.Message, description: str):
        embed = discord.Embed(
            description=f"<a:loading:1292980861142040606> {description}",
            color=discord.Color.blue(),
        )
        return await message.reply(embed=embed)

    async def update_embed(
        self, embed_message: discord.Message, description: str, error: bool = False
    ):
        embed = discord.Embed(
            description=f"{'<:error:1294770298649972850>' if error else '<a:loading:1292980861142040606>'} {description}",
            color=discord.Color.red() if error else discord.Color.blue(),
        )
        await embed_message.edit(embed=embed)

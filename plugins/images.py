from base64 import b64encode

import discord
from aiohttp import ClientSession

from ._plugin import AIPlugin


class ImagesPlugin(AIPlugin):
    name = "Image Processing"

    def __init__(self, session: ClientSession):
        self.session = session

        super().__init__()

    async def process(
        self,
        initial_message: discord.Message,
        message: discord.Message,
        content: str,
        context: list,
    ):
        should_search, confidence = await self.should_use_plugin(message)
        if should_search:
            await self.update_embed(
                initial_message, "AI is typing a response based on the image..."
            )
            prompt = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": content},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"{message.attachments[0].url}"},
                        },
                    ],
                },
            ]

            return prompt
        return None

    async def should_use_plugin(self, message: discord.Message):
        if message.attachments:
            if message.attachments[0].content_type.startswith("image/"):
                return True, 1.00
        return False, 0.00

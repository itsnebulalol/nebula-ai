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
        if message.attachments and message.attachments[0].content_type.startswith(
            "image/"
        ):
            await self.update_embed(initial_message, "Processing the image...")
            resp = await self.session.get(message.attachments[0].url)
            enc = b64encode(await resp.read()).decode("utf-8")

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
                            "image_url": {"url": f"data:image/png;base64,{enc}"},
                        },
                    ],
                },
            ]

            return prompt
        return None

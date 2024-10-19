from base64 import b64decode
from datetime import datetime
from io import BytesIO

import discord
from aiohttp import ClientSession
from openai import AsyncOpenAI

from utils.colorthief import get_color

from ._plugin import AIPlugin


class ImageGenPlugin(AIPlugin):
    name = "Image Generation"
    normal_takeover = True

    def __init__(self, session: ClientSession, client: AsyncOpenAI, ai_config):
        self.session = session
        self.client = client
        self.ai_config = ai_config

        self.trigger_phrases = [
            "generate an image",
            "generate a photo",
            "generate a picture",
            "create an image",
            "create a photo",
            "create a picture",
            "create art",
            "visualize this",
        ]

        super().__init__()

    async def process(
        self,
        initial_message,
        message,
        content,
        context,
    ):
        should_use, confidence = await self.should_use_stable_diffusion(content)
        if should_use:
            await self.update_embed(initial_message, "Generating image...")
            stable_diffusion_prompt = await self.generate_stable_diffusion_prompt(
                content
            )

            async with self.session.post(
                "http://127.0.0.1:8000/api/generate",
                json={"prompt": stable_diffusion_prompt, "use_openvino": True},
            ) as resp:
                if resp.status == 200:
                    response = await resp.json()
                    image_data = response["images"][0]
                    latency = response["latency"]

                    image_bytes = b64decode(image_data)

                    image_stream = BytesIO(image_bytes)
                    image_stream.seek(0)

                    file = discord.File(
                        fp=image_stream, filename=f"SPOILER_generated_image.png"
                    )

                    plugin_info = f"Used plugin: {self.name}{f' ({confidence} confidence) ' if confidence else ''}\n\n"
                    embed = discord.Embed(
                        description=f"{plugin_info}time {latency}s",
                        color=await get_color(message.author.avatar.url),
                        timestamp=datetime.now(),
                    )
                    embed.set_footer(
                        text=f"Request from {message.author.name}",
                        icon_url=message.author.avatar.url,
                    )
                    await initial_message.edit(embed=embed, attachments=[file])

                    return True
                else:
                    await self.update_embed(
                        initial_message, "Failed to generate image.", error=True
                    )
                    return True

        return None

    async def should_use_stable_diffusion(self, content):
        if any(phrase in content.lower() for phrase in self.trigger_phrases):
            return True, 1.0

        return False, 0.0

    async def generate_stable_diffusion_prompt(self, content: str):
        cont = content
        for word in self.trigger_phrases:
            cont = cont.replace(word, "").strip()

        cont = " ".join(cont.split())
        return cont

        # maybe add this back in the future...

        prompt = [
            {
                "role": "system",
                "content": self.get_prompt("generate"),
            },
            {
                "role": "user",
                "content": f"Craft a detailed image description based on this input: '{content}'\n\nRemember, provide ONLY the prompt for the image generation AI, without any explanation or commentary.",
            },
        ]

        completion = await self.client.chat.completions.create(
            model=self.ai_config["models"]["text"],
            messages=prompt,
        )
        generated_prompt = completion.choices[0].message.content.strip()

        return generated_prompt

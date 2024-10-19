import asyncio
from tempfile import TemporaryDirectory

import discord
from aiohttp import ClientSession
from whisper import Whisper
from yt_dlp import YoutubeDL

from ._plugin import AIPlugin


class YouTubePlugin(AIPlugin):
    name = "YouTube"

    def __init__(self, session: ClientSession, whisper_model: Whisper):
        self.session = session
        self.whisper_model = whisper_model

        self.ydl_opts = {
            "format": "bestaudio/best",
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "wav",
                    "preferredquality": "192",
                }
            ],
        }

        super().__init__()

    async def process(
        self,
        initial_message: discord.Message,
        message: discord.Message,
        content: str,
        context: list,
    ):
        if "youtube.com" in content or "youtu.be" in content:
            await self.update_embed(initial_message, "Processing the YouTube video...")
            video_url = self.extract_youtube_url(content)
            print(video_url)
            if not video_url:
                await self.update_embed(
                    initial_message, "Invalid YouTube URL provided.", error=True
                )
                return None

            title, transcript = await self.transcribe_youtube_video(video_url)
            print(transcript)
            if not transcript:
                await self.update_embed(
                    initial_message, "Failed to transcribe the video.", error=True
                )
                return None

            await self.update_embed(initial_message, "AI is analyzing the video...")
            prompt = [
                {
                    "role": "user",
                    "content": f"User query: {content}\n\nYouTube video title: {title}\n\nYouTube video transcript:\n{transcript}\n\nPlease follow what the user asked you to do and/or say using this information.",
                },
            ]

            return prompt
        return None

    def extract_youtube_url(self, content):
        words = content.split()
        for word in words:
            if "youtube.com" in word or "youtu.be" in word:
                return word
        return None

    async def transcribe_youtube_video(self, video_url: str):
        try:
            loop = asyncio.get_event_loop()

            with TemporaryDirectory() as temp:
                opts = self.ydl_opts.copy()
                opts["outtmpl"] = f"{temp}/%(id)s.%(ext)s"

                with YoutubeDL(opts) as ydl:
                    info = await loop.run_in_executor(
                        None, lambda: ydl.extract_info(video_url, download=False)
                    )
                    title = info["title"]
                    video_id = info["id"]

                    await loop.run_in_executor(None, lambda: ydl.download([video_url]))

                audio_file = f"{temp}/{video_id}.wav"

                result = await loop.run_in_executor(
                    None, lambda: self.whisper_model.transcribe(audio_file)
                )

            return title, result["text"]
        except Exception as e:
            print(f"Error transcribing YouTube video: {e}")
            return None

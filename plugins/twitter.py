import re

import discord
from aiohttp import ClientSession
from bs4 import BeautifulSoup

from ._plugin import AIPlugin


class TwitterPlugin(AIPlugin):
    name = "Twitter"

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
        twitter_username = self.extract_twitter_username(content)
        if twitter_username:
            await self.update_embed(
                initial_message, f"Fetching tweets from @{twitter_username}..."
            )
            tweets = await self.fetch_tweets(twitter_username)
            if not tweets:
                await self.update_embed(
                    initial_message,
                    f"Failed to fetch tweets from @{twitter_username}.",
                    error=True,
                )
                return None

            await self.update_embed(initial_message, "AI is analyzing the tweets...")
            prompt = [
                {
                    "role": "user",
                    "content": f"User query: {content}\n\nRecent tweets from @{twitter_username}:\n{tweets}\n\nPlease analyze these tweets and respond to the user's query.",
                },
            ]

            return prompt
        return None

    def extract_twitter_username(self, content):
        match = re.search(r"@(\w+)", content)
        return match.group(1) if match else None

    async def fetch_tweets(self, username, num_tweets=5):
        url = f"https://nitter.privacydev.net/{username}"
        async with self.session.get(url) as response:
            if response.status != 200:
                return None

            html = await response.text()
            soup = BeautifulSoup(html, "html.parser")
            tweets = soup.find_all("div", class_="tweet-content", limit=num_tweets)

            if not tweets:
                return None

            formatted_tweets = []
            for tweet in tweets:
                formatted_tweets.append(tweet.get_text(strip=True))
            print(formatted_tweets)

            return "\n\n".join(formatted_tweets)

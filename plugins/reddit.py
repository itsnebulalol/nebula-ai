from re import search

import discord
from asyncpraw import Reddit

from ._plugin import AIPlugin


class RedditPlugin(AIPlugin):
    name = "Reddit"

    def __init__(self, client_id, client_secret, user_agent):
        self.reddit = Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
            read_only=True,
        )

        super().__init__()

    async def plugin_unload(self):
        await self.reddit.close()

    async def process(
        self,
        initial_message: discord.Message,
        message: discord.Message,
        content: str,
        context: list,
    ):
        reddit_url = self.extract_reddit_url(content)
        if reddit_url:
            await self.update_embed(initial_message, "Fetching data from Reddit...")
            title, content, comments = await self.fetch_data(reddit_url)
            if not comments:
                await self.update_embed(
                    initial_message,
                    "Failed to fetch data.",
                    error=True,
                )
                return None

            await self.update_embed(initial_message, "AI is analyzing the post...")
            prompt = [
                {
                    "role": "user",
                    "content": f"User query: {content}\n\nReddit post title: {title}\n\nReddit post content:\n{content}\n\nTop Reddit post comments:\n```\n{comments}\n```\n\nPlease analyze these comments and follow what the user asked you to do and/or say using this information. Do not write a response to this unless asked, only follow what the user asked.",
                },
            ]

            return prompt
        return None

    async def fetch_data(self, submission_url, limit=10):
        try:
            submission = await self.reddit.submission(url=submission_url)
            title = submission.title
            content = submission.selftext

            await submission.comments.replace_more(limit=0)
            comments = []
            for top_level_comment in submission.comments[:limit]:
                comments.append(top_level_comment.body)

            return title, content, "\n\n".join(comments)
        except Exception as e:
            print(f"Error fetching Reddit comments: {e}")
            return None

    def extract_reddit_url(self, content):
        match = search(
            r"(https?://(?:www\.)?(?:old\.)?reddit\.com/r/[A-Za-z0-9_]+/(?:comments|s)/[A-Za-z0-9_]+(?:/[^/ ]+)?(?:/\w+)?)|(https?://(?:www\.)?redd\.it/[A-Za-z0-9]+)",
            content,
        )
        return match.group(0) if match else None

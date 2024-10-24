from random import choice
from re import search

import discord
from aiohttp import ClientSession
from bs4 import BeautifulSoup
from duckduckgo_search import AsyncDDGS
from openai import AsyncOpenAI

from ._plugin import AIPlugin


class WebPlugin(AIPlugin):
    name = "Web Search"

    def __init__(self, session: ClientSession, client: AsyncOpenAI, ai_config, proxies):
        self.session = session
        self.client = client
        self.ai_config = ai_config
        self.proxies = proxies

        super().__init__()

    async def process(
        self,
        initial_message: discord.Message,
        message: discord.Message,
        content: str,
        context: list,
    ):
        should_search, confidence = await self.should_search_web(message)
        if should_search:
            await self.update_embed(
                initial_message, "Determining the best search query..."
            )
            search_query = await self.get_search_query(content, context)

            await self.update_embed(initial_message, "Searching the web...")
            search_results = await self.search_web(
                search_query.split('"')[1] if '"' in search_query else search_query
            )

            await self.update_embed(
                initial_message, "AI is typing a response based on web results..."
            )
            prompt = [
                {
                    "role": "user",
                    "content": f"User query: {content}\n\nAI given search query: '{search_query}'\n\nRelevant web results:\n{search_results}\n\nPlease provide a response based on this information. Usage of the web information may not be necessary.",
                },
            ]

            return prompt, confidence
        return None

    async def should_search_web(self, message: discord.Message) -> bool:
        if message.attachments:
            if message.attachments[0].content_type.startswith("image/"):
                return False

        text = message.content.lower().strip().lstrip(";")

        prompt = [
            {
                "role": "system",
                "content": self.get_prompt("check"),
            },
            {
                "role": "user",
                "content": f"Determine the confidence level for using the AI Web Search plugin based on this input and the guidelines given to you: '{text}'\n\nRemember, provide only a number between 0.00 and 1.00, representing your confidence level. Do not write any other text. If you cannot do it, provide 0.00 to save time and resources.",
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
            if res >= 0.50:
                return True, res
            else:
                return False, res
        except:
            return False, 0.00

    async def get_search_query(self, content: str, context: list) -> str:
        context_text = [msg["content"] for msg in context if msg["role"] == "assistant"]
        prompt = [
            {
                "role": "system",
                "content": self.get_prompt("generate"),
            },
            {
                "role": "user",
                "content": f"Generate a search query based on this input and the previously given guidelines: '{content}'\n\nPrevious context (ignore unless absolutely necessary):\n{context_text}\n\nRemember, provide ONLY the search query.",
            },
        ]

        completion = await self.client.chat.completions.create(
            model=self.ai_config["models"]["text"],
            messages=prompt,
        )
        print(completion.choices[0].message.content.strip())

        return completion.choices[0].message.content.strip()

    async def search_web(self, query: str, num_results: int = 3) -> str:
        proxy = choice(self.proxies) if self.proxies else None
        results = await AsyncDDGS(proxy=proxy).atext(
            query, safesearch="on", max_results=num_results, backend="api"
        )

        if not results:
            return "No results found."

        scraped_content = []
        for result in results:
            content = await self.scrape_website(result["href"])
            scraped_content.append(
                f"Title: {result['title']}\nSearch Engine Preview: {result['body']}\nPage Content: {content}"
            )

        return "\n\n".join(scraped_content)

    async def scrape_website(self, url: str) -> str:
        try:
            async with self.session.get(url, timeout=10) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, "html.parser")

                    for element in soup(
                        ["header", "nav", "footer", "aside", "script", "style"]
                    ):
                        element.decompose()

                    main_content = (
                        soup.find("main")
                        or soup.find("article")
                        or soup.find("div", class_="content")
                    )

                    if main_content:
                        text = main_content.get_text(separator=" ", strip=True)
                    else:
                        text = soup.body.get_text(separator=" ", strip=True)

                    lines = (line.strip() for line in text.splitlines())
                    chunks = (
                        phrase.strip() for line in lines for phrase in line.split("  ")
                    )
                    text = " ".join(chunk for chunk in chunks if chunk)

                    # For some websites
                    comments = soup.find_all("div", class_=["comment", "md"])
                    if comments:
                        comment_text = "\n".join(
                            comment.get_text(strip=True) for comment in comments[:5]
                        )
                        text += f"\n\nTop comments:\n{comment_text}"

                    return text[:2000]
                else:
                    return "No content available"
        except:
            return "No content available"

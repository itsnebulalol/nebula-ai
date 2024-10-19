from enum import Enum

from aiohttp import ClientSession

from ._scraper import SearchEngine


class SearXNG(SearchEngine):
    name = "SearXNG"

    def __init__(self, url: str, session: ClientSession):
        self.url = url
        self.session = session

        super().__init__()

    class SafeSearch(Enum):
        NONE = 0
        MODERATE = 1
        STRICT = 2

    async def scrape(
        self, query: str, max_results: int, safe_search: SafeSearch = SafeSearch.STRICT
    ):
        req = self.session.get(
            self.url, params={"q": query, "format": "json", "safesearch": safe_search}
        )

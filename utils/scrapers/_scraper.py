from abc import ABC, abstractmethod


class SearchEngine(ABC):
    name = "Scraper"

    def __init__(self):
        pass

    @abstractmethod
    async def scrape(self, query: str, max_results: int, safe_search: any):
        pass

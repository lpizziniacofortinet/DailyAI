"""Tavily search provider implementation for enhanced AI search grounding."""

import os
from typing import List, Optional
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from dailyai.logging_config import get_logger
from dailyai.models.article import DomainType, RawSourceItem
from dailyai.services.search.base import BaseSearchEngine

logger = get_logger("search.tavily")


class TavilySearchEngine(BaseSearchEngine):
    """Tavily API search provider."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("TAVILY_API_KEY")
        if not self.api_key:
            raise ValueError("Tavily API key is missing.")

    @retry(
        reraise=False,
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=3),
    )
    def search(
        self,
        query: str,
        domain: DomainType,
        max_results: int = 5,
        lookback_hours: int = 24,
    ) -> List[RawSourceItem]:
        """Perform search using Tavily API."""
        results: List[RawSourceItem] = []
        url = "https://api.tavily.com/search"
        payload = {
            "api_key": self.api_key,
            "query": query,
            "search_depth": "advanced",
            "topic": "news" if lookback_hours <= 72 else "general",
            "max_results": max_results,
            "days": max(1, lookback_hours // 24),
        }

        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()

                for hit in data.get("results", []):
                    title = hit.get("title", "").strip()
                    item_url = hit.get("url", "").strip()
                    snippet = hit.get("content", "").strip()
                    published_date = hit.get("published_date")

                    if title and item_url:
                        results.append(
                            RawSourceItem(
                                title=title,
                                url=item_url,
                                snippet=snippet,
                                source_name="Tavily Search",
                                published_at=published_date,
                                domain=domain,
                                raw_metadata={"score": hit.get("score")},
                            )
                        )
            logger.info(f"Tavily search returned {len(results)} items for '{query}'")
        except Exception as e:
            logger.warning(f"Tavily search failed for '{query}': {e}")

        return results

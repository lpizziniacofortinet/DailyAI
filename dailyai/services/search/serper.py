"""Google Serper search provider implementation."""

import os
from typing import List, Optional
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from dailyai.logging_config import get_logger
from dailyai.models.article import DomainType, RawSourceItem
from dailyai.services.search.base import BaseSearchEngine

logger = get_logger("search.serper")


class SerperSearchEngine(BaseSearchEngine):
    """Google Serper API search provider."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("SERPER_API_KEY")
        if not self.api_key:
            raise ValueError("Serper API key is missing.")

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
        """Perform search using Google Serper API."""
        results: List[RawSourceItem] = []
        url = "https://google.serper.dev/news"
        headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "q": query,
            "num": max_results,
            "tbs": "qdr:d" if lookback_hours <= 24 else "qdr:w",
        }

        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()

                for hit in data.get("news", []):
                    title = hit.get("title", "").strip()
                    item_url = hit.get("link", "").strip()
                    snippet = hit.get("snippet", "").strip()
                    source_name = hit.get("source", "Google News").strip()
                    date_str = hit.get("date")

                    if title and item_url:
                        results.append(
                            RawSourceItem(
                                title=title,
                                url=item_url,
                                snippet=snippet,
                                source_name=source_name,
                                published_at=date_str,
                                domain=domain,
                                raw_metadata=hit,
                            )
                        )
            logger.info(f"Serper search returned {len(results)} items for '{query}'")
        except Exception as e:
            logger.warning(f"Serper search failed for '{query}': {e}")

        return results

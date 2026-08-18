"""DuckDuckGo search provider implementation for live intelligence gathering."""

import re
from typing import List
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from dailyai.logging_config import get_logger
from dailyai.models.article import DomainType, RawSourceItem
from dailyai.services.search.base import BaseSearchEngine

logger = get_logger("search.duckduckgo")


def clean_snippet(text: str) -> str:
    """Clean HTML tags and whitespace from search snippets."""
    if not text:
        return ""
    # Strip HTML tags
    soup = BeautifulSoup(text, "html.parser")
    cleaned = soup.get_text(separator=" ")
    # Normalize whitespaces
    return " ".join(cleaned.split())


class DuckDuckGoSearchEngine(BaseSearchEngine):
    """Search engine powered by DuckDuckGo News and Web Search."""

    def __init__(self, timeout: int = 15):
        self.timeout = timeout

    @retry(
        reraise=False,
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=4),
    )
    def search(
        self,
        query: str,
        domain: DomainType,
        max_results: int = 5,
        lookback_hours: int = 24,
    ) -> List[RawSourceItem]:
        """Perform search on DuckDuckGo News and Text."""
        results: List[RawSourceItem] = []
        timelimit = "d" if lookback_hours <= 36 else "w"

        try:
            from duckduckgo_search import DDGS

            with DDGS(timeout=self.timeout) as ddgs:
                # 1. First attempt DuckDuckGo News
                try:
                    news_hits = list(
                        ddgs.news(
                            keywords=query,
                            region="wt-wt",
                            safesearch="moderate",
                            timelimit=timelimit,
                            max_results=max_results,
                        )
                    )
                    for hit in news_hits:
                        title = hit.get("title", "").strip()
                        url = hit.get("url", "").strip()
                        body = clean_snippet(hit.get("body", ""))
                        source_name = hit.get("source", "News Source").strip()
                        date_str = hit.get("date")

                        if url and title:
                            results.append(
                                RawSourceItem(
                                    title=title,
                                    url=url,
                                    snippet=body,
                                    source_name=source_name,
                                    published_at=date_str,
                                    domain=domain,
                                    raw_metadata={"type": "ddg_news", **hit},
                                )
                            )
                except Exception as e:
                    logger.debug(f"DDG news search for '{query}' encountered: {e}")

                # 2. If news returned fewer results than desired, supplement with standard text search
                if len(results) < max_results:
                    remaining = max_results - len(results)
                    try:
                        text_hits = list(
                            ddgs.text(
                                keywords=query,
                                region="wt-wt",
                                safesearch="moderate",
                                timelimit=timelimit,
                                max_results=remaining + 2,
                            )
                        )
                        for hit in text_hits:
                            title = hit.get("title", "").strip()
                            url = hit.get("href", "").strip()
                            body = clean_snippet(hit.get("body", ""))

                            # Filter out obviously historical articles from previous years
                            lower_text = f"{title} {body}".lower()
                            stale_years = ["2018", "2019", "2020", "2021", "2022", "2023", "2024"]
                            if any(y in lower_text for y in stale_years) and not any(y in lower_text for y in ["2025", "2026"]):
                                continue

                            # Deduplicate within this query batch
                            if url and title and not any(r.url == url for r in results):
                                results.append(
                                    RawSourceItem(
                                        title=title,
                                        url=url,
                                        snippet=body,
                                        source_name="Web Search",
                                        published_at=None,
                                        domain=domain,
                                        raw_metadata={"type": "ddg_text", **hit},
                                    )
                                )
                    except Exception as e:
                        logger.debug(f"DDG text search for '{query}' encountered: {e}")

        except Exception as e:
            logger.warning(f"DuckDuckGo search error for query '{query}': {e}")

        logger.info(f"DuckDuckGo gathered {len(results)} source items for query: '{query}'")
        return results[:max_results]

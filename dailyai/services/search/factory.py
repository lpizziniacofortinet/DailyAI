"""Factory for instantiating search engines."""

from typing import Optional
from dailyai.config import Settings, get_settings
from dailyai.logging_config import get_logger
from dailyai.services.search.base import BaseSearchEngine
from dailyai.services.search.duckduckgo import DuckDuckGoSearchEngine
from dailyai.services.search.mock import MockSearchEngine
from dailyai.services.search.serper import SerperSearchEngine
from dailyai.services.search.tavily import TavilySearchEngine

logger = get_logger("search.factory")


def get_search_engine(settings: Optional[Settings] = None) -> BaseSearchEngine:
    """Instantiate and return search engine based on configuration."""
    cfg = settings or get_settings()
    provider = cfg.search_provider.lower()

    if provider == "mock":
        return MockSearchEngine()

    if provider == "tavily":
        key = cfg.tavily_api_key.get_secret_value() if cfg.tavily_api_key else None
        if key:
            return TavilySearchEngine(api_key=key)
        logger.warning("TAVILY_API_KEY missing, falling back to DuckDuckGo.")
        return DuckDuckGoSearchEngine()

    if provider == "serper":
        key = cfg.serper_api_key.get_secret_value() if cfg.serper_api_key else None
        if key:
            return SerperSearchEngine(api_key=key)
        logger.warning("SERPER_API_KEY missing, falling back to DuckDuckGo.")
        return DuckDuckGoSearchEngine()

    if provider == "duckduckgo":
        return DuckDuckGoSearchEngine()

    if provider == "rss_only":
        # Returns empty search engine so only RSS feed aggregator is used
        return MockSearchEngine()

    logger.warning(f"Unknown search provider '{provider}', defaulting to DuckDuckGo.")
    return DuckDuckGoSearchEngine()

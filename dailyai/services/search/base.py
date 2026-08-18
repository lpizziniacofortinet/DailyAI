"""Abstract base interface for search engines and intelligence aggregators."""

from abc import ABC, abstractmethod
from typing import List
from dailyai.models.article import DomainType, RawSourceItem


class BaseSearchEngine(ABC):
    """Abstract interface for intelligence source gatherers."""

    @abstractmethod
    def search(
        self,
        query: str,
        domain: DomainType,
        max_results: int = 5,
        lookback_hours: int = 24,
    ) -> List[RawSourceItem]:
        """Execute query search and return raw source hits."""
        pass

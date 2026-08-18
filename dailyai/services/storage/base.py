"""Base interface for article deduplication and pipeline run storage."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from dailyai.models.pipeline import PipelineRunReport


class BaseDeduplicationStore(ABC):
    """Abstract base class for persistent deduplication and history tracking."""

    @abstractmethod
    def is_url_processed(self, url: str) -> bool:
        """Check whether a URL has already been processed or published."""
        pass

    @abstractmethod
    def is_title_duplicate(self, title: str, threshold: float = 0.85) -> bool:
        """Check whether a headline is a near-duplicate of an already published article."""
        pass

    @abstractmethod
    def mark_url_seen(
        self,
        url: str,
        title: str,
        domain: str,
        draft_id: Optional[str] = None,
    ) -> None:
        """Record a newly discovered URL to prevent re-processing."""
        pass

    @abstractmethod
    def mark_article_published(
        self,
        url: str,
        title: str,
        domain: str,
        newsletter_id: str,
    ) -> None:
        """Record an article as officially published in a newsletter."""
        pass

    @abstractmethod
    def record_pipeline_run(self, report: PipelineRunReport) -> None:
        """Store pipeline execution report and metrics."""
        pass

    @abstractmethod
    def get_recent_runs(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieve recent pipeline run summaries."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Cleanly close database connections."""
        pass

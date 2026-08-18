"""Data models for newsletter generation and delivery."""

from datetime import datetime, timezone
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from dailyai.models.article import DomainType
from dailyai.models.fact_check import VerifiedArticle


class NewsletterSection(BaseModel):
    """Section within the newsletter representing one technology domain."""
    domain: DomainType = Field(..., description="Domain category")
    title: str = Field(..., description="Display title for section")
    articles: List[VerifiedArticle] = Field(
        default_factory=list,
        description="List of verified articles for this section, ordered by priority",
    )
    section_summary: Optional[str] = Field(
        default=None,
        description="Executive takeaway summarizing domain developments for the day",
    )


class Newsletter(BaseModel):
    """Complete assembled newsletter ready for distribution."""
    id: str = Field(..., description="Unique newsletter run ID")
    title: str = Field(..., description="Subject line / Main headline")
    date_str: str = Field(..., description="Formatted publication date (e.g. 'Monday, August 17, 2026')")
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Generation timestamp",
    )
    sections: List[NewsletterSection] = Field(
        default_factory=list,
        description="List of domain sections",
    )
    total_articles: int = Field(default=0, description="Total number of articles included")
    html_content: str = Field(default="", description="Rendered responsive HTML email body")
    text_content: str = Field(default="", description="Rendered plain-text email body")
    recipients: List[str] = Field(default_factory=list, description="Target recipient email addresses")
    delivered_successfully: bool = Field(default=False, description="Whether delivery succeeded")
    delivery_timestamp: Optional[datetime] = Field(default=None, description="Time of delivery dispatch")

    @property
    def domain_counts(self) -> Dict[str, int]:
        """Count of articles per domain."""
        return {section.domain.value: len(section.articles) for section in self.sections}

"""Data models for raw source items, article drafts, and verified articles."""

from datetime import datetime, timezone
from enum import Enum
import hashlib
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, HttpUrl


class DomainType(str, Enum):
    """Supported technology domains for intelligence tracking."""
    AI = "ai"
    CYBERSECURITY = "cybersecurity"
    V2X = "v2x"

    @property
    def display_name(self) -> str:
        """User-friendly title with icon for newsletters."""
        mapping = {
            DomainType.AI: "🤖 Artificial Intelligence",
            DomainType.CYBERSECURITY: "🔐 Cybersecurity",
            DomainType.V2X: "🚗 V2X & Automotive Technology",
        }
        return mapping[self]

    @property
    def badge_color(self) -> str:
        """Tailored color code for email badges."""
        mapping = {
            DomainType.AI: "#2563EB",           # Royal blue
            DomainType.CYBERSECURITY: "#DC2626", # Deep crimson
            DomainType.V2X: "#059669",          # Forest emerald
        }
        return mapping[self]


class RawSourceItem(BaseModel):
    """Raw hit collected from web search engine or RSS feed."""
    title: str = Field(..., description="Title of the source item or article")
    url: str = Field(..., description="Source URL")
    snippet: str = Field(default="", description="Snippet, summary, or extracted text")
    source_name: str = Field(default="Web", description="Name of publisher or feed")
    published_at: Optional[str] = Field(default=None, description="Reported publication date string")
    domain: DomainType = Field(..., description="Target technology domain")
    raw_metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional crawler metadata")

    @property
    def url_hash(self) -> str:
        """Deterministic SHA-256 hash of normalized URL."""
        from dailyai.services.storage.sqlite import compute_url_hash
        return compute_url_hash(self.url)


class ArticleDraft(BaseModel):
    """Structured research draft produced by Agent 1 (Research & Intelligence)."""
    id: str = Field(..., description="Unique draft identifier")
    domain: DomainType = Field(..., description="Technology domain")
    title: str = Field(..., description="Clear, descriptive headline")
    summary: str = Field(..., description="Concise factual summary of the development")
    key_points: List[str] = Field(default_factory=list, description="Bullet points of key information")
    facts: List[str] = Field(default_factory=list, description="Verified or claimed factual assertions")
    opinions_or_speculation: List[str] = Field(default_factory=list, description="Speculative points or opinions")
    
    source_url: str = Field(..., description="Direct link to primary source")
    original_source_name: str = Field(default="Unknown", description="Original publisher/organization")
    original_source_url: Optional[str] = Field(default=None, description="Original source URL if syndicated")
    published_date: Optional[str] = Field(default=None, description="Publication date (YYYY-MM-DD if available)")
    
    relevance_score: float = Field(default=0.8, ge=0.0, le=1.0, description="Estimated domain relevance")
    entities_mentioned: List[str] = Field(default_factory=list, description="Key entities (companies, models, orgs)")
    cve_identifiers: List[str] = Field(default_factory=list, description="CVE IDs if cybersecurity related")
    standards_mentioned: List[str] = Field(default_factory=list, description="Relevant technical standards (e.g. 3GPP Rel-17, ISO 26262)")
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Draft generation timestamp")

    @property
    def canonical_url(self) -> str:
        """Get canonical URL, prioritizing original source URL if available."""
        return self.original_source_url or self.source_url

    @property
    def url_hash(self) -> str:
        """Deterministic hash for deduplication."""
        from dailyai.services.storage.sqlite import compute_url_hash
        return compute_url_hash(self.canonical_url)

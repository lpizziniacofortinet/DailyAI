"""Data models for fact-checking, verification results, and verified articles."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from dailyai.models.article import ArticleDraft, DomainType


class VerificationStatus(str, Enum):
    """Status of fact-checking evaluation."""
    VERIFIED = "VERIFIED"
    VERIFIED_WITH_CAVEATS = "VERIFIED_WITH_CAVEATS"
    REJECTED = "REJECTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class ClaimCheck(BaseModel):
    """Result of cross-referencing an individual claim."""
    claim: str = Field(..., description="The factual assertion checked")
    status: str = Field(
        ...,
        description="Claim evaluation status: 'VERIFIED', 'REFUTED', 'UNVERIFIED', 'SPECULATIVE'",
    )
    reasoning: str = Field(..., description="Explanation of verification or grounds for skepticism")
    cross_references: List[str] = Field(
        default_factory=list,
        description="URLs, publications, or sources corroborating/refuting the claim",
    )


class VerificationResult(BaseModel):
    """Comprehensive fact-checking evaluation produced by Agent 2."""
    status: VerificationStatus = Field(..., description="Overall verification verdict")
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Assessed factual reliability score (0.0 to 1.0)",
    )
    claims_checked: List[ClaimCheck] = Field(
        default_factory=list,
        description="Detailed checks for specific claims",
    )
    hallucinations_detected: List[str] = Field(
        default_factory=list,
        description="Identified hallucinations or unsubstantiated claims",
    )
    technical_terms_verified: List[str] = Field(
        default_factory=list,
        description="Verified technical terminology, acronyms, and product names",
    )
    cve_validation_notes: Optional[str] = Field(
        default=None,
        description="Validation feedback for CVE identifiers (e.g. format, valid disclosure)",
    )
    standards_validation_notes: Optional[str] = Field(
        default=None,
        description="Validation feedback for standards (e.g. 3GPP, IEEE, ISO, NIST)",
    )
    rejection_reason: Optional[str] = Field(
        default=None,
        description="Reason for rejection if status is REJECTED or INSUFFICIENT_EVIDENCE",
    )
    quality_score: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Writing clarity and technical depth quality score",
    )
    cross_check_sources: List[str] = Field(
        default_factory=list,
        description="Additional sources consulted during cross-check",
    )


class VerifiedArticle(BaseModel):
    """Article that has undergone independent verification by Agent 2."""
    draft: ArticleDraft = Field(..., description="Original draft from Agent 1")
    verification: VerificationResult = Field(..., description="Verification evaluation report")
    
    final_headline: str = Field(..., description="Validated, non-sensational headline")
    final_summary: str = Field(..., description="Factual, refined summary")
    impact_analysis: str = Field(
        default="",
        description="Explanation of why this development is significant to the domain",
    )
    caveats_and_uncertainty: List[str] = Field(
        default_factory=list,
        description="Explicit warnings or context regarding speculation or early stage claims",
    )
    
    relevance_rank: int = Field(
        default=1,
        ge=1,
        description="Priority ranking within its category (1 = top priority)",
    )
    is_approved: bool = Field(
        default=True,
        description="Whether this article passed quality gating and is cleared for newsletter publication",
    )
    verification_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Time when verification was performed",
    )

    @property
    def domain(self) -> DomainType:
        return self.draft.domain

    @property
    def source_url(self) -> str:
        return self.draft.canonical_url

    @property
    def original_source_name(self) -> str:
        return self.draft.original_source_name

    @property
    def published_date(self) -> Optional[str]:
        return self.draft.published_date

    @property
    def cve_identifiers(self) -> List[str]:
        return self.draft.cve_identifiers

    @property
    def standards_mentioned(self) -> List[str]:
        return self.draft.standards_mentioned

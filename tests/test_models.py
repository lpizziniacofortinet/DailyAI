"""Unit tests for data models."""

from datetime import datetime, timezone
import pytest

from dailyai.models.article import ArticleDraft, DomainType, RawSourceItem
from dailyai.models.fact_check import (
    ClaimCheck,
    VerificationResult,
    VerificationStatus,
    VerifiedArticle,
)
from dailyai.models.newsletter import Newsletter, NewsletterSection
from dailyai.models.pipeline import AgentExecutionRecord, PipelineRunReport


def test_domain_types():
    """Verify DomainType enum values, display names, and colors."""
    assert DomainType.AI.value == "ai"
    assert "🤖" in DomainType.AI.display_name
    assert DomainType.CYBERSECURITY.value == "cybersecurity"
    assert "🔐" in DomainType.CYBERSECURITY.display_name
    assert DomainType.V2X.value == "v2x"
    assert "🚗" in DomainType.V2X.display_name
    assert DomainType.AI.badge_color.startswith("#")


def test_raw_source_item_hash():
    """Verify URL hashing and normalization on RawSourceItem."""
    item1 = RawSourceItem(
        title="Test Article",
        url="https://example.com/news/123?utm_source=twitter&ref=abc",
        snippet="Snippet text",
        domain=DomainType.AI,
    )
    item2 = RawSourceItem(
        title="Test Article",
        url="https://example.com/news/123",
        snippet="Different snippet",
        domain=DomainType.AI,
    )
    # Normalized URLs should produce the exact same hash
    assert item1.url_hash == item2.url_hash


def test_article_draft_serialization(sample_draft):
    """Verify ArticleDraft serialization and deserialization."""
    json_data = sample_draft.model_dump_json()
    reconstructed = ArticleDraft.model_validate_json(json_data)
    assert reconstructed.id == sample_draft.id
    assert reconstructed.domain == DomainType.AI
    assert len(reconstructed.key_points) == 2


def test_verified_article_properties(sample_verified_article):
    """Verify convenience properties on VerifiedArticle."""
    assert sample_verified_article.domain == DomainType.AI
    assert sample_verified_article.source_url == "https://arxiv.org/abs/2608.10982"
    assert sample_verified_article.is_approved is True
    assert sample_verified_article.verification.status == VerificationStatus.VERIFIED


def test_newsletter_model(sample_verified_article):
    """Verify Newsletter and NewsletterSection models."""
    section = NewsletterSection(
        domain=DomainType.AI,
        title=DomainType.AI.display_name,
        articles=[sample_verified_article],
    )
    newsletter = Newsletter(
        id="nl-test-01",
        title="[DailyAI] Test Brief",
        date_str="Monday, Aug 17, 2026",
        sections=[section],
        total_articles=1,
        recipients=["user@example.com"],
    )
    assert newsletter.total_articles == 1
    assert newsletter.domain_counts["ai"] == 1


def test_pipeline_run_report_serialization():
    """Verify PipelineRunReport JSON roundtrip."""
    record = AgentExecutionRecord(
        agent_name="Test Agent",
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        duration_seconds=1.23,
        items_in=5,
        items_out=3,
        status="SUCCESS",
    )
    report = PipelineRunReport(
        run_id="run-test-01",
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        duration_seconds=3.45,
        drafts_collected=5,
        articles_verified=3,
        articles_rejected=2,
        articles_published=3,
        agent_records=[record],
        delivery_status="DELIVERED",
        is_success=True,
    )
    json_str = report.model_dump_json()
    reconstructed = PipelineRunReport.model_validate_json(json_str)
    assert reconstructed.run_id == "run-test-01"
    assert reconstructed.is_success is True
    assert len(reconstructed.agent_records) == 1

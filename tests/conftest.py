"""Shared pytest fixtures and test utilities."""

import os
from pathlib import Path
import tempfile
import pytest
from pydantic import SecretStr

from dailyai.config import Settings, reset_settings
from dailyai.models.article import ArticleDraft, DomainType, RawSourceItem
from dailyai.models.fact_check import ClaimCheck, VerificationResult, VerificationStatus, VerifiedArticle
from dailyai.services.llm.mock import MockLLMClient
from dailyai.services.search.mock import MockSearchEngine
from dailyai.services.storage.sqlite import SQLiteDeduplicationStore


@pytest.fixture
def temp_db_path():
    """Create a temporary SQLite database file path."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = Path(f.name)
    yield path
    if path.exists():
        try:
            path.unlink()
        except Exception:
            pass


@pytest.fixture
def temp_output_dir():
    """Create a temporary output directory for newsletter files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def test_settings(temp_db_path, temp_output_dir):
    """Provide isolated test Settings instance."""
    settings = Settings(
        llm_provider="mock",
        search_provider="mock",
        gemini_api_key=SecretStr("test-gemini-key"),
        openai_api_key=SecretStr("test-openai-key"),
        email_enabled=False,
        email_recipients=["test1@example.com", "test2@example.com"],
        database_path=temp_db_path,
        output_dir=temp_output_dir,
        search_queries_per_category=2,
        max_search_results_per_query=3,
        max_articles_per_category=3,
        lookback_hours=24,
        enable_rss_feeds=False,
        fact_check_strict_mode=True,
        min_confidence_score=0.75,
        dry_run=False,
    )
    reset_settings(settings)
    return settings


@pytest.fixture
def mock_llm():
    """Provide Mock LLM client."""
    return MockLLMClient()


@pytest.fixture
def mock_search():
    """Provide Mock Search engine."""
    return MockSearchEngine()


@pytest.fixture
def sqlite_store(temp_db_path):
    """Provide clean SQLiteDeduplicationStore instance."""
    store = SQLiteDeduplicationStore(db_path=temp_db_path)
    yield store
    store.close()


@pytest.fixture
def sample_raw_item():
    """Provide a sample raw source item."""
    return RawSourceItem(
        title="DeepSeek Unveils Open Weights for DeepSeek-R2",
        url="https://arxiv.org/abs/2608.10982",
        snippet="Researchers present an enhanced reasoning model architecture with open weights.",
        source_name="arXiv CS.AI",
        published_at="2026-08-17 08:00:00",
        domain=DomainType.AI,
    )


@pytest.fixture
def sample_draft():
    """Provide a sample ArticleDraft."""
    return ArticleDraft(
        id="draft-test-101",
        domain=DomainType.AI,
        title="DeepSeek Unveils Open Weights for DeepSeek-R2",
        summary="Researchers present an enhanced reasoning model architecture with open weights.",
        key_points=[
            "Achieves 94% on Math-500 benchmark",
            "Full model weights and training checkpoints made open source",
        ],
        facts=[
            "Benchmarked against standardized reasoning suites",
        ],
        opinions_or_speculation=[],
        source_url="https://arxiv.org/abs/2608.10982",
        original_source_name="arXiv",
        published_date=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).date().isoformat(),
        relevance_score=0.95,
        entities_mentioned=["DeepSeek", "Math-500"],
    )


@pytest.fixture
def sample_cyber_draft():
    """Provide a sample Cybersecurity ArticleDraft with CVE."""
    return ArticleDraft(
        id="draft-test-cyber",
        domain=DomainType.CYBERSECURITY,
        title="CISA Adds Critical Linux Kernel Flaw (CVE-2026-2189) to KEV Catalog",
        summary="CISA urges immediate patching of root privilege escalation in Linux eBPF subsystem.",
        key_points=[
            "Actively exploited in the wild",
            "Affects kernel versions 6.1 through 6.8",
        ],
        facts=[
            "Assigned CVSS score of 9.8",
        ],
        opinions_or_speculation=[],
        source_url="https://www.cisa.gov/news-events/cybersecurity-advisories/aa26-229a",
        original_source_name="CISA Advisories",
        published_date="2026-08-17",
        relevance_score=0.98,
        entities_mentioned=["CISA", "Linux Kernel"],
        cve_identifiers=["CVE-2026-2189"],
    )


@pytest.fixture
def sample_v2x_draft():
    """Provide a sample V2X ArticleDraft with standards."""
    return ArticleDraft(
        id="draft-test-v2x",
        domain=DomainType.V2X,
        title="5GAA and Qualcomm Validate 3GPP Release 18 C-V2X Direct Sidelink",
        summary="Field tests prove sub-10ms latency for pedestrian safety alerts via C-V2X sidelink.",
        key_points=[
            "Direct vehicle-to-pedestrian smartphone alerts",
            "Tested under 3GPP Release 18 specifications",
        ],
        facts=[
            "Demonstrated 99.99% packet delivery reliability",
        ],
        opinions_or_speculation=[],
        source_url="https://5gaa.org/news/release-18-cv2x-vru-validation",
        original_source_name="5GAA",
        published_date="2026-08-17",
        relevance_score=0.92,
        entities_mentioned=["5GAA", "Qualcomm"],
        standards_mentioned=["3GPP Release 18", "ISO 26262"],
    )


@pytest.fixture
def sample_verified_article(sample_draft):
    """Provide a sample VerifiedArticle."""
    verification = VerificationResult(
        status=VerificationStatus.VERIFIED,
        confidence_score=0.95,
        claims_checked=[
            ClaimCheck(
                claim="Model weights released under open source license.",
                status="VERIFIED",
                reasoning="Confirmed via repository commit history.",
                cross_references=["https://arxiv.org/abs/2608.10982"],
            )
        ],
        quality_score=0.9,
    )
    return VerifiedArticle(
        draft=sample_draft,
        verification=verification,
        final_headline=sample_draft.title,
        final_summary=sample_draft.summary,
        impact_analysis="Dramatically lowers inference costs for open reasoning models in production.",
        caveats_and_uncertainty=[],
        relevance_rank=1,
        is_approved=True,
    )

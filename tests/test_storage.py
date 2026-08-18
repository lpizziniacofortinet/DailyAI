"""Unit tests for SQLite persistent deduplication and history storage."""

from datetime import datetime, timezone
import pytest

from dailyai.models.pipeline import PipelineRunReport
from dailyai.services.storage.sqlite import SQLiteDeduplicationStore, compute_url_hash, normalize_title, normalize_url


def test_url_normalization():
    """Verify URL cleaning and normalization."""
    url1 = "https://EXAMPLE.com/path/article/?utm_source=twitter&utm_medium=social"
    url2 = "https://example.com/path/article"
    assert normalize_url(url1) == normalize_url(url2)
    assert compute_url_hash(url1) == compute_url_hash(url2)


def test_title_normalization():
    """Verify title normalization strips punctuation and spaces."""
    t1 = "DeepSeek-R2: Open Weights Released (94% Accuracy)!"
    t2 = "deepseek r2 open weights released 94 accuracy"
    assert normalize_title(t1) == normalize_title(t2)


def test_seen_url_deduplication(sqlite_store):
    """Verify marking URLs as seen and checking them."""
    test_url = "https://arxiv.org/abs/2608.99999"
    assert not sqlite_store.is_url_processed(test_url)

    sqlite_store.mark_url_seen(
        url=test_url,
        title="Test Seen Article",
        domain="ai",
        draft_id="draft-001",
    )
    assert sqlite_store.is_url_processed(test_url)


def test_published_article_deduplication(sqlite_store):
    """Verify marking published articles and duplicate title checking."""
    test_url = "https://cisa.gov/news/cve-2026-9999"
    title = "CISA Issues Emergency Directive on Linux Kernel Vulnerability"

    assert not sqlite_store.is_url_processed(test_url)
    assert not sqlite_store.is_title_duplicate(title)

    sqlite_store.mark_article_published(
        url=test_url,
        title=title,
        domain="cybersecurity",
        newsletter_id="nl-001",
    )

    # URL should now be recognized as processed
    assert sqlite_store.is_url_processed(test_url)

    # Near-identical headline should trigger duplicate check
    near_duplicate = "CISA Issues Emergency Directive Regarding Linux Kernel Vulnerability"
    assert sqlite_store.is_title_duplicate(near_duplicate, threshold=0.80)

    # Unrelated headline should not trigger duplicate check
    unrelated = "Qualcomm Announces Next-Gen Snapdragon Digital Chassis with V2X"
    assert not sqlite_store.is_title_duplicate(unrelated)


def test_pipeline_run_persistence(sqlite_store):
    """Verify saving and retrieving pipeline run execution records."""
    report = PipelineRunReport(
        run_id="run-persist-test",
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        duration_seconds=2.45,
        drafts_collected=6,
        articles_verified=4,
        articles_rejected=2,
        articles_published=4,
        delivery_status="DELIVERED",
        is_success=True,
    )

    sqlite_store.record_pipeline_run(report)
    recent = sqlite_store.get_recent_runs(limit=5)
    assert len(recent) >= 1
    assert recent[0]["run_id"] == "run-persist-test"
    assert recent[0]["articles_published"] == 4

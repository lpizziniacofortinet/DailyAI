"""Unit tests for Agent 1 — Research & Intelligence Agent."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import pytest

from dailyai.agents.research_agent import ResearchAgent, is_article_outdated
from dailyai.models.article import ArticleDraft, DomainType, RawSourceItem
from dailyai.services.search.base import BaseSearchEngine
from dailyai.services.search.rss import parse_feed_dates
from dailyai.temporal import DateEvaluationStatus, evaluate_publication_date

FIXED_NOW = datetime(2026, 11, 24, 12, 0, 0, tzinfo=timezone.utc)


def fixed_clock() -> datetime:
    return FIXED_NOW


class StaticSearchEngine(BaseSearchEngine):
    """Search engine returning caller-provided RawSourceItem entries."""

    def __init__(self, items_by_domain):
        self.items_by_domain = items_by_domain

    def search(self, query, domain, max_results=5, lookback_hours=24):
        return list(self.items_by_domain.get(domain, []))[:max_results]


def test_research_agent_execution(test_settings, mock_llm, mock_search, sqlite_store):
    """Verify Agent 1 collects, deduplicates, and synthesizes drafts across all 3 domains."""
    agent = ResearchAgent(
        settings=test_settings,
        llm_client=mock_llm,
        search_engine=mock_search,
        storage=sqlite_store,
    )

    result = agent.execute(None)
    assert result.success is True
    assert result.output is not None
    drafts = result.output

    # Should have gathered items from all 3 domains
    domains_present = {d.domain for d in drafts}
    assert DomainType.AI in domains_present
    assert DomainType.CYBERSECURITY in domains_present
    assert DomainType.V2X in domains_present

    # Verify structured fields
    for draft in drafts:
        assert isinstance(draft, ArticleDraft)
        assert len(draft.title) > 0
        assert len(draft.summary) > 0
        assert draft.source_url.startswith("http")
        assert draft.relevance_score >= 0.5


def test_research_agent_deduplication(test_settings, mock_llm, mock_search, sqlite_store):
    """Verify Agent 1 skips URLs that already exist in persistent storage."""
    agent = ResearchAgent(
        settings=test_settings,
        llm_client=mock_llm,
        search_engine=mock_search,
        storage=sqlite_store,
    )

    # First run: should synthesize drafts
    res1 = agent.execute(None)
    assert res1.success is True
    first_count = len(res1.output)
    assert first_count > 0

    # Simulate publication persistence (Agent 3 records published articles)
    for draft in res1.output:
        sqlite_store.mark_article_published(
            url=draft.source_url,
            title=draft.title,
            domain=draft.domain.value,
            newsletter_id="nl-dedup-test",
        )

    # Second run without dry_run: all previously published URLs should now be deduplicated/skipped
    res2 = agent.execute(None)
    assert res2.success is True
    assert len(res2.output) == 0  # All duplicates filtered out


@pytest.mark.parametrize(
    "date_str,expected_status,strict_reject,nonstrict_reject,unverified",
    [
        # Missing dates
        (None, DateEvaluationStatus.MISSING, True, False, True),
        ("", DateEvaluationStatus.MISSING, True, False, True),
        ("   ", DateEvaluationStatus.MISSING, True, False, True),
        # Malformed dates
        ("not-a-date", DateEvaluationStatus.MALFORMED, True, False, True),
        ("2026-99-99", DateEvaluationStatus.MALFORMED, True, False, True),
        # Timezone-aware fresh dates
        ("2026-11-24T10:00:00Z", DateEvaluationStatus.FRESH, False, False, False),
        ("2026-11-24T14:00:00+02:00", DateEvaluationStatus.FRESH, False, False, False),
        ("2026-11-24T05:00:00-05:00", DateEvaluationStatus.FRESH, False, False, False),
        # Timezone-naive fresh date (interpreted as UTC)
        ("2026-11-24 10:00:00", DateEvaluationStatus.FRESH, False, False, False),
        # Exact lower boundary: 24h lookback + 48h buffer = 72h before FIXED_NOW
        ("2026-11-21T12:00:00Z", DateEvaluationStatus.FRESH, False, False, False),
        # Just past lower boundary (stale by 1 second)
        ("2026-11-21T11:59:59Z", DateEvaluationStatus.STALE, True, True, False),
        # Clearly stale
        ("2025-01-01", DateEvaluationStatus.STALE, True, True, False),
        # Exact upper boundary: +24h future tolerance
        ("2026-11-25T12:00:00Z", DateEvaluationStatus.FRESH, False, False, False),
        # Just past upper boundary (future by 1 second)
        ("2026-11-25T12:00:01Z", DateEvaluationStatus.FUTURE, True, True, False),
        # Clearly future
        ("2026-12-01T00:00:00Z", DateEvaluationStatus.FUTURE, True, True, False),
    ],
)
def test_evaluate_publication_date_matrix(
    date_str, expected_status, strict_reject, nonstrict_reject, unverified
):
    """Verify freshness evaluation across missing, malformed, tz-aware, tz-naive, boundary, stale, and future dates."""
    ev = evaluate_publication_date(date_str, lookback_hours=24, buffer_days=2, now=FIXED_NOW)
    assert ev.status == expected_status
    assert ev.date_unverified is unverified
    assert ev.should_reject(strict_mode=True) is strict_reject
    assert ev.should_reject(strict_mode=False) is nonstrict_reject
    assert is_article_outdated(date_str, lookback_hours=24, now=FIXED_NOW, strict_mode=True) is strict_reject
    assert is_article_outdated(date_str, lookback_hours=24, now=FIXED_NOW, strict_mode=False) is nonstrict_reject


def test_research_agent_strict_mode_quarantines_missing_and_malformed_dates(
    test_settings, mock_llm, sqlite_store
):
    """In strict mode, ResearchAgent fails closed on missing, malformed, stale, and future dates."""
    test_settings.fact_check_strict_mode = True
    test_settings.max_search_results_per_query = 5
    items = {
        DomainType.AI: [
            RawSourceItem(
                title="Valid Recent AI Model Release Announcement",
                url="https://example.com/ai-valid",
                snippet="Verified release.",
                source_name="arXiv",
                published_at="2026-11-24T09:00:00Z",
                updated_at="2026-11-24T11:00:00Z",
                event_date="2026-12-10",
                domain=DomainType.AI,
            ),
            RawSourceItem(
                title="Article With Missing Publication Date Metadata",
                url="https://example.com/ai-missing-date",
                snippet="No date.",
                source_name="Blog",
                published_at=None,
                domain=DomainType.AI,
            ),
            RawSourceItem(
                title="Article With Malformed Publication Date Metadata",
                url="https://example.com/ai-bad-date",
                snippet="Bad date.",
                source_name="Blog",
                published_at="not-a-valid-date",
                domain=DomainType.AI,
            ),
            RawSourceItem(
                title="Article With Future Publication Date Metadata",
                url="https://example.com/ai-future-date",
                snippet="Future date.",
                source_name="Blog",
                published_at="2026-12-01T00:00:00Z",
                domain=DomainType.AI,
            ),
        ]
    }
    agent = ResearchAgent(
        settings=test_settings,
        llm_client=mock_llm,
        search_engine=StaticSearchEngine(items),
        storage=sqlite_store,
        clock=fixed_clock,
    )

    result = agent.execute(None)
    assert result.success is True
    assert len(result.output) == 1
    draft = result.output[0]
    assert draft.source_url == "https://example.com/ai-valid"
    assert draft.date_unverified is False
    # Temporal fields remain distinct
    assert draft.published_date == "2026-11-24T09:00:00Z" or draft.published_date == "2026-11-24"
    assert draft.updated_date == "2026-11-24T11:00:00Z"
    assert draft.event_date == "2026-12-10"

    # Quarantine audit records capture all 3 rejected items with reasons
    assert len(agent.last_quarantined_items) == 3
    statuses = {q["status"] for q in agent.last_quarantined_items}
    assert statuses == {"MISSING", "MALFORMED", "FUTURE"}
    assert all(q["reason"] for q in agent.last_quarantined_items)
    assert result.record.metadata["quarantined_count"] == "3"


def test_research_agent_nonstrict_mode_flags_date_unverified(
    test_settings, mock_llm, sqlite_store
):
    """In non-strict mode, missing/malformed dates are retained ONLY with date_unverified=True, while stale/future are still rejected."""
    test_settings.fact_check_strict_mode = False
    items = {
        DomainType.AI: [
            RawSourceItem(
                title="Non-Strict Missing Publication Date Article",
                url="https://example.com/nonstrict-missing",
                snippet="Missing date item.",
                source_name="Blog",
                published_at=None,
                domain=DomainType.AI,
            ),
            RawSourceItem(
                title="Non-Strict Malformed Publication Date Article",
                url="https://example.com/nonstrict-malformed",
                snippet="Malformed date item.",
                source_name="Blog",
                published_at="garbage-date",
                domain=DomainType.AI,
            ),
            RawSourceItem(
                title="Non-Strict Stale Publication Date Article",
                url="https://example.com/nonstrict-stale",
                snippet="Stale item.",
                source_name="Blog",
                published_at="2025-05-01",
                domain=DomainType.AI,
            ),
        ]
    }
    agent = ResearchAgent(
        settings=test_settings,
        llm_client=mock_llm,
        search_engine=StaticSearchEngine(items),
        storage=sqlite_store,
        clock=fixed_clock,
    )

    result = agent.execute(None)
    assert result.success is True
    assert len(result.output) == 2
    assert all(d.date_unverified is True for d in result.output)
    assert result.record.metadata["date_unverified_count"] == "2"
    # Stale item was still quarantined
    assert len(agent.last_quarantined_items) == 1
    assert agent.last_quarantined_items[0]["status"] == "STALE"


def test_rss_parse_feed_dates_keeps_published_and_updated_separate():
    """RSS parser does not conflate updated_parsed with published_parsed."""
    entry = SimpleNamespace(
        published_parsed=None,
        published=None,
        updated_parsed=FIXED_NOW.timetuple(),
        updated=None,
    )
    pub_dt, upd_dt = parse_feed_dates(entry)
    assert pub_dt is None
    assert upd_dt is not None


def test_research_agent_isolates_optional_rss_failure(test_settings, mock_llm, mock_search, sqlite_store):
    """A failing optional RSS source does not prevent web search collection from succeeding."""
    test_settings.enable_rss_feeds = True

    class BrokenRSS:
        def fetch_domain_feeds(self, **kwargs):
            raise RuntimeError("RSS endpoint timeout")

    agent = ResearchAgent(
        settings=test_settings,
        llm_client=mock_llm,
        search_engine=mock_search,
        rss_aggregator=BrokenRSS(),
        storage=sqlite_store,
    )
    result = agent.execute(None)
    assert result.success is True
    assert result.record.status == "PARTIAL_SUCCESS"
    assert len(result.output) > 0
    assert any("RSS endpoint timeout" in e for e in result.errors)

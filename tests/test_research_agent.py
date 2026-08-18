"""Unit tests for Agent 1 — Research & Intelligence Agent."""

import pytest
from dailyai.agents.research_agent import ResearchAgent
from dailyai.models.article import ArticleDraft, DomainType


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

    # First run: should synthesize drafts and record URLs
    res1 = agent.execute(None)
    assert res1.success is True
    first_count = len(res1.output)
    assert first_count > 0

    # Second run without dry_run: all previous URLs should now be deduplicated/skipped
    res2 = agent.execute(None)
    assert res2.success is True
    assert len(res2.output) == 0  # All duplicates filtered out

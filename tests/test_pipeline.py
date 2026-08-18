"""Integration tests for the end-to-end PipelineOrchestrator."""

import pytest
from dailyai.agents.fact_check_agent import FactCheckAgent
from dailyai.agents.newsletter_agent import NewsletterAgent
from dailyai.agents.research_agent import ResearchAgent
from dailyai.models.article import DomainType
from dailyai.pipeline.orchestrator import PipelineOrchestrator
from dailyai.services.delivery.mock import MockDeliveryChannel


def test_pipeline_orchestrator_e2e(test_settings, mock_llm, mock_search, sqlite_store):
    """Verify complete end-to-end flow: Agent 1 -> Agent 2 -> Agent 3 -> Output & Storage."""
    mock_delivery = MockDeliveryChannel()

    research_agent = ResearchAgent(
        settings=test_settings,
        llm_client=mock_llm,
        search_engine=mock_search,
        storage=sqlite_store,
    )
    fact_check_agent = FactCheckAgent(
        settings=test_settings,
        llm_client=mock_llm,
        search_engine=mock_search,
    )
    newsletter_agent = NewsletterAgent(
        settings=test_settings,
        llm_client=mock_llm,
        delivery_channels=[mock_delivery],
        storage=sqlite_store,
    )

    orchestrator = PipelineOrchestrator(
        settings=test_settings,
        research_agent=research_agent,
        fact_check_agent=fact_check_agent,
        newsletter_agent=newsletter_agent,
        storage=sqlite_store,
    )

    report, newsletter = orchestrator.run()

    assert report.is_success is True
    assert report.drafts_collected > 0
    assert report.articles_verified > 0
    assert report.articles_published > 0
    assert len(report.agent_records) == 3
    assert report.delivery_status == "DELIVERED"

    # Verify domain breakdown
    assert DomainType.AI in report.domain_breakdown
    assert DomainType.CYBERSECURITY in report.domain_breakdown
    assert DomainType.V2X in report.domain_breakdown

    # Verify newsletter was generated and passed to delivery channel
    assert newsletter is not None
    assert len(mock_delivery.delivered_newsletters) == 1

    # Verify report was recorded in SQLite database
    recent = sqlite_store.get_recent_runs(limit=1)
    assert len(recent) == 1
    assert recent[0]["run_id"] == report.run_id


def test_pipeline_orchestrator_subsequent_run_deduplication(test_settings, mock_llm, mock_search, sqlite_store):
    """Verify that subsequent run does not re-publish previously published articles."""
    mock_delivery = MockDeliveryChannel()

    research_agent = ResearchAgent(
        settings=test_settings,
        llm_client=mock_llm,
        search_engine=mock_search,
        storage=sqlite_store,
    )
    fact_check_agent = FactCheckAgent(
        settings=test_settings,
        llm_client=mock_llm,
        search_engine=mock_search,
    )
    newsletter_agent = NewsletterAgent(
        settings=test_settings,
        llm_client=mock_llm,
        delivery_channels=[mock_delivery],
        storage=sqlite_store,
    )

    orchestrator = PipelineOrchestrator(
        settings=test_settings,
        research_agent=research_agent,
        fact_check_agent=fact_check_agent,
        newsletter_agent=newsletter_agent,
        storage=sqlite_store,
    )

    # First run publishes articles
    report1, _ = orchestrator.run()
    assert report1.articles_published > 0

    # Second run finds no novel articles (all previously seen URLs deduplicated)
    report2, nl2 = orchestrator.run()
    assert report2.drafts_collected == 0
    assert report2.articles_published == 0

"""Unit tests for Agent 3 — Newsletter & Delivery Agent."""

import pytest
from dailyai.agents.newsletter_agent import NewsletterAgent
from dailyai.models.article import DomainType
from dailyai.models.fact_check import VerificationResult, VerificationStatus, VerifiedArticle
from dailyai.models.newsletter import Newsletter
from dailyai.services.delivery.mock import MockDeliveryChannel


def test_newsletter_agent_assembly_and_rendering(test_settings, mock_llm, sqlite_store, sample_verified_article):
    """Verify Agent 3 groups articles into 3 sections, renders HTML/text, and distributes."""
    mock_delivery = MockDeliveryChannel()
    agent = NewsletterAgent(
        settings=test_settings,
        llm_client=mock_llm,
        delivery_channels=[mock_delivery],
        storage=sqlite_store,
    )

    result = agent.execute([sample_verified_article])
    assert result.success is True
    newsletter = result.output

    assert isinstance(newsletter, Newsletter)
    assert newsletter.total_articles == 1
    assert len(newsletter.sections) == 3
    assert len(newsletter.html_content) > 100
    assert len(newsletter.text_content) > 100
    assert "DailyAI" in newsletter.html_content
    assert sample_verified_article.final_headline in newsletter.html_content
    assert sample_verified_article.final_headline in newsletter.text_content

    # Verify mock delivery was invoked
    assert len(mock_delivery.delivered_newsletters) == 1
    assert mock_delivery.delivered_newsletters[0].id == newsletter.id

    # Verify published article was recorded in SQLite storage
    assert sqlite_store.is_url_processed(sample_verified_article.source_url)


def test_newsletter_agent_empty_articles(test_settings, mock_llm, sqlite_store):
    """Verify Agent 3 handles runs with zero verified articles gracefully."""
    mock_delivery = MockDeliveryChannel()
    agent = NewsletterAgent(
        settings=test_settings,
        llm_client=mock_llm,
        delivery_channels=[mock_delivery],
        storage=sqlite_store,
    )

    result = agent.execute([])
    assert result.success is True
    newsletter = result.output
    assert newsletter.total_articles == 0
    assert len(newsletter.html_content) > 0

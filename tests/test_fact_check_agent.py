"""Unit tests for Agent 2 — Fact-Checking & Quality Gate."""

import pytest
from dailyai.agents.fact_check_agent import FactCheckAgent
from dailyai.models.article import ArticleDraft, DomainType
from dailyai.models.fact_check import VerificationStatus, VerifiedArticle


def test_fact_check_agent_approval(test_settings, mock_llm, mock_search, sample_draft, sample_cyber_draft, sample_v2x_draft):
    """Verify Agent 2 verifies and approves credible drafts."""
    agent = FactCheckAgent(
        settings=test_settings,
        llm_client=mock_llm,
        search_engine=mock_search,
    )

    drafts = [sample_draft, sample_cyber_draft, sample_v2x_draft]
    result = agent.execute(drafts)

    assert result.success is True
    verified_list = result.output
    assert len(verified_list) == 3

    for item in verified_list:
        assert isinstance(item, VerifiedArticle)
        assert item.is_approved is True
        assert item.verification.confidence_score >= test_settings.min_confidence_score
        assert len(item.final_headline) > 0
        assert len(item.impact_analysis) > 0


def test_fact_check_cve_and_standards_validation(test_settings, mock_llm, sample_cyber_draft, sample_v2x_draft):
    """Verify technical identifier validation (CVE format and standard names)."""
    agent = FactCheckAgent(settings=test_settings, llm_client=mock_llm)

    # Valid CVE
    notes = agent._validate_technical_identifiers(sample_cyber_draft)
    assert notes["cve"] is not None
    assert "CVE-2026-2189" in notes["cve"]

    # Valid Standard
    notes_v2x = agent._validate_technical_identifiers(sample_v2x_draft)
    assert notes_v2x["standards"] is not None
    assert "3GPP Release 18" in notes_v2x["standards"]


def test_fact_check_rejection(test_settings, mock_llm):
    """Verify low-confidence or uncorroborated drafts are rejected."""
    agent = FactCheckAgent(settings=test_settings, llm_client=mock_llm)

    unverifiable_draft = ArticleDraft(
        id="draft-bogus-01",
        domain=DomainType.CYBERSECURITY,
        title="Unverified claim from unknown blog test_reject",
        summary="Rumor says quantum computers broke AES-256 yesterday.",
        source_url="https://unknown-unverified-blog.xyz/rumor",
        relevance_score=0.3,
    )

    result = agent.execute([unverifiable_draft])
    assert result.success is True
    # The rejected article should NOT appear in the final approved list
    assert len(result.output) == 0


def test_fact_check_empty_input(test_settings, mock_llm):
    """Verify graceful handling when no drafts are provided."""
    agent = FactCheckAgent(settings=test_settings, llm_client=mock_llm)
    result = agent.execute([])
    assert result.success is True
    assert result.output == []


def test_fact_check_outdated_article_rejection(test_settings, mock_llm):
    """Verify historical articles from previous years (e.g. 2022) are rejected."""
    agent = FactCheckAgent(settings=test_settings, llm_client=mock_llm)

    old_draft = ArticleDraft(
        id="draft-old-chatgpt",
        domain=DomainType.AI,
        title="OpenAI Announces ChatGPT Preview",
        summary="OpenAI launches experimental research preview of conversational AI model.",
        source_url="https://openai.com/blog/chatgpt",
        published_date="2022-11-30",
        relevance_score=0.9,
    )

    result = agent.execute([old_draft])
    assert result.success is True
    # The outdated article must be rejected
    assert len(result.output) == 0

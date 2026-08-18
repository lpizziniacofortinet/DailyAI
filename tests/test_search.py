"""Unit tests for search and RSS services."""

import pytest
from dailyai.models.article import DomainType
from dailyai.services.search.factory import get_search_engine
from dailyai.services.search.mock import MockSearchEngine
from dailyai.services.search.rss import clean_html_summary


def test_mock_search_engine():
    """Verify MockSearchEngine returns domain-appropriate items."""
    engine = MockSearchEngine()
    
    ai_hits = engine.search("AI LLM reasoning", DomainType.AI, max_results=2)
    assert len(ai_hits) == 2
    assert ai_hits[0].domain == DomainType.AI
    assert "DeepSeek" in ai_hits[0].title or "Anthropic" in ai_hits[0].title or "PyTorch" in ai_hits[0].title

    cyber_hits = engine.search("Linux CVE", DomainType.CYBERSECURITY, max_results=3)
    assert len(cyber_hits) == 3
    assert cyber_hits[0].domain == DomainType.CYBERSECURITY
    assert any("CVE" in h.title or "NIST" in h.title for h in cyber_hits)

    v2x_hits = engine.search("5GAA C-V2X", DomainType.V2X, max_results=2)
    assert len(v2x_hits) == 2
    assert v2x_hits[0].domain == DomainType.V2X


def test_clean_html_summary():
    """Verify HTML tag stripping and whitespace normalization."""
    html_text = "<p>This is <b>bold</b> text with <a href='https://example.com'>a link</a> and &amp; entities.</p>"
    cleaned = clean_html_summary(html_text)
    assert "<p>" not in cleaned
    assert "bold text with a link" in cleaned


def test_search_factory(test_settings):
    """Verify search engine factory instantiation."""
    engine = get_search_engine(test_settings)
    assert isinstance(engine, MockSearchEngine)

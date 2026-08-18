"""Unit tests for LLM client abstraction and providers."""

import pytest
from pydantic import BaseModel, Field

from dailyai.services.llm.base import BaseLLMClient
from dailyai.services.llm.factory import get_llm_client
from dailyai.services.llm.mock import MockLLMClient


class SampleSchema(BaseModel):
    name: str = Field(default="test")
    score: float = Field(default=0.9)


def test_mock_llm_text():
    """Verify MockLLM generates coherent text."""
    llm = MockLLMClient()
    text = llm.generate_text("Please provide a newsletter subject line")
    assert len(text) > 10
    assert "DailyAI" in text or "Intelligence" in text


def test_mock_llm_structured():
    """Verify MockLLM returns valid structured model."""
    llm = MockLLMClient()
    result = llm.generate_structured("prompt", SampleSchema)
    assert isinstance(result, SampleSchema)


def test_json_block_extraction():
    """Verify JSON code fence extraction in BaseLLMClient."""
    class DummyClient(BaseLLMClient):
        def generate_text(self, prompt, system_instruction=None, temperature=0.2):
            return ""
        def generate_structured(self, prompt, response_model, system_instruction=None, temperature=0.1):
            return response_model()

    client = DummyClient()
    markdown_json = "```json\n{\"name\": \"extracted\", \"score\": 0.95}\n```"
    parsed = client._parse_pydantic_from_json_text(markdown_json, SampleSchema)
    assert parsed.name == "extracted"
    assert parsed.score == 0.95


def test_llm_factory(test_settings):
    """Verify LLM factory returns MockLLMClient when configured."""
    client = get_llm_client(test_settings)
    assert isinstance(client, MockLLMClient)

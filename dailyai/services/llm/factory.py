"""Factory for initializing configured LLM client."""

from typing import Optional
from dailyai.config import Settings, get_settings
from dailyai.logging_config import get_logger
from dailyai.services.llm.base import BaseLLMClient
from dailyai.services.llm.gemini import GeminiLLMClient
from dailyai.services.llm.mock import MockLLMClient
from dailyai.services.llm.openai_provider import OpenAILLMClient

logger = get_logger("llm.factory")


def get_llm_client(settings: Optional[Settings] = None) -> BaseLLMClient:
    """Instantiate and return LLM client based on configuration.

    Falls back gracefully if API keys are missing or invalid.
    """
    cfg = settings or get_settings()
    provider = cfg.llm_provider.lower()

    if provider == "mock":
        return MockLLMClient()

    if provider == "gemini":
        gemini_key = cfg.gemini_api_key.get_secret_value() if cfg.gemini_api_key else None
        if not gemini_key:
            logger.warning("No GEMINI_API_KEY provided in configuration. Falling back to MockLLMClient.")
            return MockLLMClient()
        return GeminiLLMClient(
            api_key=gemini_key,
            model_name=cfg.gemini_model,
        )

    if provider == "openai":
        openai_key = cfg.openai_api_key.get_secret_value() if cfg.openai_api_key else None
        if not openai_key:
            logger.warning("No OPENAI_API_KEY provided in configuration. Falling back to MockLLMClient.")
            return MockLLMClient()
        return OpenAILLMClient(
            api_key=openai_key,
            model_name=cfg.openai_model,
            base_url=cfg.openai_base_url,
        )

    logger.warning(f"Unknown LLM provider '{provider}', falling back to MockLLMClient.")
    return MockLLMClient()

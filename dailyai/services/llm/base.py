"""Abstract base interface for LLM providers with structured output support."""

from abc import ABC, abstractmethod
import json
import re
from typing import Any, Dict, Optional, Type, TypeVar
from pydantic import BaseModel
from dailyai.logging_config import get_logger

logger = get_logger("llm.base")

T = TypeVar("T", bound=BaseModel)


class BaseLLMClient(ABC):
    """Abstract interface for LLM backends (Gemini, OpenAI, Mock, etc.)."""

    @abstractmethod
    def generate_text(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2,
    ) -> str:
        """Generate unstructured text response from prompt."""
        pass

    @abstractmethod
    def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_instruction: Optional[str] = None,
        temperature: float = 0.1,
    ) -> T:
        """Generate structured output validated against a Pydantic model."""
        pass

    def _extract_json_block(self, raw_text: str) -> str:
        """Helper to extract JSON from markdown code fences or raw string."""
        raw_text = raw_text.strip()
        # Look for ```json ... ``` or ``` ... ```
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw_text)
        if match:
            return match.group(1).strip()
        
        # Look for { ... } or [ ... ]
        first_brace = raw_text.find("{")
        last_brace = raw_text.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            return raw_text[first_brace : last_brace + 1].strip()

        first_bracket = raw_text.find("[")
        last_bracket = raw_text.rfind("]")
        if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
            return raw_text[first_bracket : last_bracket + 1].strip()

        return raw_text

    def _parse_pydantic_from_json_text(
        self,
        raw_text: str,
        response_model: Type[T],
    ) -> T:
        """Safely parse Pydantic model from LLM JSON response text."""
        json_str = self._extract_json_block(raw_text)
        try:
            parsed = json.loads(json_str)
            return response_model.model_validate(parsed)
        except Exception as err:
            logger.error(f"Failed to parse Pydantic model {response_model.__name__} from JSON: {err}\nRaw text: {raw_text[:300]}...")
            raise

"""Google Gemini LLM provider implementation using google-genai SDK."""

import os
from typing import Optional, Type, TypeVar
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from dailyai.logging_config import get_logger
from dailyai.services.llm.base import BaseLLMClient

logger = get_logger("llm.gemini")

T = TypeVar("T", bound=BaseModel)


class GeminiLLMClient(BaseLLMClient):
    """Client for Google Gemini models via the google-genai SDK."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gemini-2.5-flash",
    ):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Gemini API key not found. Please provide GEMINI_API_KEY in environment or .env file."
            )
        self.model_name = model_name

        try:
            from google import genai
            self.client = genai.Client(api_key=self.api_key)
            logger.info(f"Initialized Gemini client with model '{self.model_name}'")
        except Exception as e:
            logger.error(f"Failed to initialize google-genai Client: {e}")
            raise

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1.5, min=2, max=10),
    )
    def _handle_gemini_error(self, e: Exception) -> None:
        """Check for API key invalid errors and provide friendly explanation."""
        err_str = str(e)
        if "API_KEY_INVALID" in err_str or "API key not valid" in err_str:
            raise ValueError(
                "Your GEMINI_API_KEY is invalid or unauthorized.\n"
                "1. Get a free API key at: https://aistudio.google.com/app/apikey\n"
                "2. Add it to your .env file as: GEMINI_API_KEY=AIzaSy...\n"
                "3. Or run offline with mock mode using: python3 -m dailyai run --provider mock"
            ) from e

    def generate_text(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2,
    ) -> str:
        """Generate text using Gemini."""
        from google.genai import types

        config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system_instruction,
        )

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config,
            )
            if not response or not response.text:
                raise RuntimeError("Empty response received from Gemini API.")
            return response.text.strip()
        except Exception as e:
            self._handle_gemini_error(e)
            raise

    def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_instruction: Optional[str] = None,
        temperature: float = 0.1,
    ) -> T:
        """Generate structured output validated against a Pydantic model."""
        from google.genai import types

        json_instruction = (
            f"You MUST return only a single valid JSON object adhering to the schema of {response_model.__name__}. "
            "Do not include any Markdown text before or after the JSON. "
        )
        combined_sys = f"{system_instruction}\n\n{json_instruction}" if system_instruction else json_instruction

        config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=combined_sys,
            response_mime_type="application/json",
            response_schema=response_model,
        )

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config,
            )
            raw_text = response.text or ""
            return self._parse_pydantic_from_json_text(raw_text, response_model)
        except Exception as e:
            self._handle_gemini_error(e)
            logger.warning(f"Schema-constrained call failed ({e}), attempting fallback prompt-based JSON extraction...")
            # Fallback without schema parameter if SDK schema conversion hit issues
            raw_text = self.generate_text(
                prompt=f"{prompt}\n\nStrictly output valid JSON for the schema: {response_model.model_json_schema()}",
                system_instruction=combined_sys,
                temperature=temperature,
            )
            return self._parse_pydantic_from_json_text(raw_text, response_model)

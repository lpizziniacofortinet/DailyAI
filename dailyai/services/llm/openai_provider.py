"""OpenAI and OpenAI-compatible LLM provider implementation."""

import os
from typing import Optional, Type, TypeVar
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

from dailyai.logging_config import get_logger
from dailyai.services.llm.base import BaseLLMClient

logger = get_logger("llm.openai")

T = TypeVar("T", bound=BaseModel)


class OpenAILLMClient(BaseLLMClient):
    """Client for OpenAI models and OpenAI-compatible endpoints."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gpt-4o-mini",
        base_url: Optional[str] = None,
    ):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenAI API key not found. Please provide OPENAI_API_KEY in environment or .env file."
            )
        self.model_name = model_name
        self.base_url = base_url

        try:
            from openai import OpenAI
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )
            logger.info(f"Initialized OpenAI client with model '{self.model_name}' (base_url: {self.base_url or 'default'})")
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}")
            raise

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1.5, min=2, max=10),
    )
    def generate_text(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2,
    ) -> str:
        """Generate text using OpenAI API."""
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=temperature,
        )
        content = response.choices[0].message.content or ""
        return content.strip()

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1.5, min=2, max=10),
    )
    def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_instruction: Optional[str] = None,
        temperature: float = 0.1,
    ) -> T:
        """Generate structured output validated against a Pydantic model."""
        messages = []
        sys_text = (
            "You are a structured data extraction engine. "
            "You MUST respond ONLY with valid JSON conforming to the requested schema. "
        )
        if system_instruction:
            sys_text = f"{system_instruction}\n\n{sys_text}"

        messages.append({"role": "system", "content": sys_text})
        messages.append({
            "role": "user",
            "content": f"{prompt}\n\nStrictly format output as JSON adhering to this schema: {response_model.model_json_schema()}",
        })

        try:
            # Try structured outputs parse if supported
            response = self.client.beta.chat.completions.parse(
                model=self.model_name,
                messages=messages,
                response_format=response_model,
                temperature=temperature,
            )
            parsed = response.choices[0].message.parsed
            if parsed is not None:
                return parsed
        except Exception as e:
            logger.debug(f"OpenAI beta parse fell back to json_object mode: {e}")

        # Fallback to standard chat completions with json_object
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=temperature,
        )
        raw_text = response.choices[0].message.content or "{}"
        return self._parse_pydantic_from_json_text(raw_text, response_model)

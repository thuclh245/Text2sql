"""LLM client abstraction — provider-agnostic interface.

Supports OpenAI-compatible APIs. Other providers can be added by subclassing
BaseLLMClient.

Token/cost logging is mandatory for every call.
"""

from __future__ import annotations

import abc
import time
from typing import Any

from chatsql.generation.types import LLMResponse


class BaseLLMClient(abc.ABC):
    """Abstract LLM client interface."""

    @abc.abstractmethod
    def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        """Send a prompt and return a structured LLMResponse."""
        ...

    @property
    @abc.abstractmethod
    def model_name(self) -> str: ...

    @property
    @abc.abstractmethod
    def provider(self) -> str: ...

    @property
    def max_completion_tokens(self) -> int | None:
        """Configured output token budget, if known before the call."""
        return None


class OpenAIClient(BaseLLMClient):
    """OpenAI-compatible chat completion client.

    Requires `openai` package installed and OPENAI_API_KEY set.
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        temperature: float = 0.0,
        max_tokens: int = 1024,
        timeout: float = 60.0,
        max_retries: int = 3,
    ) -> None:
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._timeout = timeout
        self._max_retries = max_retries
        self._client = self._build_client()

    def _build_client(self) -> Any:
        try:
            import openai  # type: ignore[import-not-found]

            return openai.OpenAI(timeout=self._timeout, max_retries=self._max_retries)
        except ImportError as exc:
            raise ImportError("openai package not installed. Run: pip install openai") from exc

    def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        start = time.monotonic()
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            **kwargs,
        )
        elapsed = time.monotonic() - start

        choice = response.choices[0]
        usage = response.usage

        return LLMResponse(
            raw_text=choice.message.content or "",
            model=response.model,
            prompt_tokens=usage.prompt_tokens if usage else None,
            completion_tokens=usage.completion_tokens if usage else None,
            latency_seconds=elapsed,
        )

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def provider(self) -> str:
        return "openai"

    @property
    def max_completion_tokens(self) -> int | None:
        return self._max_tokens


class StubLLMClient(BaseLLMClient):
    """Deterministic stub client for testing — never calls an external API."""

    def __init__(self, fixed_response: str = "SELECT 1") -> None:
        self._response = fixed_response

    def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        return LLMResponse(
            raw_text=f"```sql\n{self._response}\n```",
            model="stub",
            prompt_tokens=len(prompt.split()),
            completion_tokens=5,
            latency_seconds=0.0,
        )

    @property
    def model_name(self) -> str:
        return "stub"

    @property
    def provider(self) -> str:
        return "stub"

    @property
    def max_completion_tokens(self) -> int | None:
        return None


def build_llm_client(model_config: dict[str, Any]) -> BaseLLMClient:
    """Build an LLM client from a config ``model`` section.

    ``provider: stub`` returns a deterministic offline client (used by tests and
    dry checks); ``provider: openai`` returns a live client.
    """
    provider = model_config.get("provider", "openai")
    if provider == "stub":
        return StubLLMClient(model_config.get("stub_response", "SELECT 1"))
    if provider == "openai":
        return OpenAIClient(
            model=model_config.get("name", "gpt-4o-mini"),
            temperature=model_config.get("temperature", 0.0),
            max_tokens=model_config.get("max_tokens", 1024),
            timeout=model_config.get("timeout_seconds", 60.0),
            max_retries=model_config.get("max_retries", 3),
        )
    raise ValueError(f"unsupported model provider: {provider!r} (expected 'openai' or 'stub')")

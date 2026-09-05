"""LLM client abstraction — provider-agnostic interface.

Supports OpenAI-compatible APIs. Other providers can be added by subclassing
BaseLLMClient.

Token/cost logging is mandatory for every call.
"""

from __future__ import annotations

import abc
import os
import time
from typing import Any

from chatsql.generation.types import LLMResponse


def format_llm_request(
    model: str,
    provider: str,
    prompt: str,
    messages: list[dict[str, str]] | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    extra_params: dict[str, Any] | None = None,
) -> str:
    """Format the payload being sent to the LLM API for inspection/debugging."""
    msgs = messages or [{"role": "user", "content": prompt}]
    lines = [
        "=" * 80,
        "[CHATSQL -> LLM API REQUEST]",
        f"Provider:    {provider}",
        f"Model:       {model}",
    ]
    if temperature is not None:
        lines.append(f"Temperature: {temperature}")
    if max_tokens is not None:
        lines.append(f"Max Tokens:  {max_tokens}")
    if extra_params:
        lines.append(f"Extra args:  {extra_params}")
    lines.append(f"Messages count: {len(msgs)}")
    for index, msg in enumerate(msgs, start=1):
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        lines.append(f"--- Message #{index} [{role}] ({len(content)} chars) ---")
        lines.append(content)
    lines.append("=" * 80)
    return "\n".join(lines)


def print_llm_request(
    model: str,
    provider: str,
    prompt: str,
    messages: list[dict[str, str]] | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    extra_params: dict[str, Any] | None = None,
) -> None:
    """Print the formatted LLM request payload to stdout."""
    print(
        format_llm_request(
            model=model,
            provider=provider,
            prompt=prompt,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            extra_params=extra_params,
        )
    )


class BaseLLMClient(abc.ABC):
    """Abstract LLM client interface."""

    def __init__(self, verbose: bool = False) -> None:
        env_verbose = os.getenv("CHATSQL_VERBOSE_LLM", "0").lower() in ("1", "true", "yes")
        self._verbose = verbose or env_verbose

    @property
    def is_verbose(self) -> bool:
        return self._verbose

    @is_verbose.setter
    def is_verbose(self, value: bool) -> None:
        self._verbose = value

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
        verbose: bool = False,
    ) -> None:
        super().__init__(verbose=verbose)
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
        is_verbose = kwargs.pop("verbose", self._verbose)
        messages = [{"role": "user", "content": prompt}]
        if is_verbose:
            print_llm_request(
                model=self._model,
                provider=self.provider,
                prompt=prompt,
                messages=messages,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
                extra_params=kwargs if kwargs else None,
            )

        start = time.monotonic()
        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
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

    def __init__(self, fixed_response: str = "SELECT 1", verbose: bool = False) -> None:
        super().__init__(verbose=verbose)
        self._response = fixed_response

    def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        is_verbose = kwargs.pop("verbose", self._verbose)
        if is_verbose:
            print_llm_request(
                model=self.model_name,
                provider=self.provider,
                prompt=prompt,
                messages=[{"role": "user", "content": prompt}],
                extra_params=kwargs if kwargs else None,
            )
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
    verbose = model_config.get("verbose", False)
    if provider == "stub":
        return StubLLMClient(model_config.get("stub_response", "SELECT 1"), verbose=verbose)
    if provider == "openai":
        return OpenAIClient(
            model=model_config.get("name", "gpt-4o-mini"),
            temperature=model_config.get("temperature", 0.0),
            max_tokens=model_config.get("max_tokens", 1024),
            timeout=model_config.get("timeout_seconds", 60.0),
            max_retries=model_config.get("max_retries", 3),
            verbose=verbose,
        )
    raise ValueError(f"unsupported model provider: {provider!r} (expected 'openai' or 'stub')")

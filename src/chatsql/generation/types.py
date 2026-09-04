"""Generation types — shared data structures for the generation layer."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class ContextView(BaseModel):
    """Rendered context passed to the LLM (schema text + question)."""

    model_config = ConfigDict(frozen=True)

    schema_text: str
    """CREATE TABLE DDL or equivalent schema representation."""

    question: str
    """Natural language question."""

    evidence_text: str | None = None
    """Optional domain hint to prepend."""

    token_estimate: int | None = None
    """Rough token count of schema_text (informational)."""


class LLMResponse(BaseModel):
    """Raw response from the LLM provider."""

    model_config = ConfigDict(frozen=True)

    raw_text: str
    """Full response text (may include chain-of-thought)."""

    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    latency_seconds: float | None = None
    metadata: dict[str, Any] = {}

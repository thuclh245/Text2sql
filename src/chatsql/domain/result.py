"""Result domain types: Prediction, ExecutionResult, ExperimentRecord."""

from __future__ import annotations

import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Prediction(BaseModel):
    """The SQL prediction produced by a Strategy for one InferenceCase."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    predicted_sql: str
    latency_seconds: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionResult(BaseModel):
    """Result of executing a SQL prediction against the target database."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    executed: bool
    """False if the SQL raised an error."""
    rows: list[list[Any]] = Field(default_factory=list)
    error: str | None = None
    execution_time_seconds: float | None = None


class ExperimentRecord(BaseModel):
    """Aggregated record for one benchmark item after evaluation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    database_id: str
    question: str
    predicted_sql: str
    executed: bool
    execution_correct: bool
    """True if predicted result matches gold result (EX metric)."""
    error: str | None = None
    latency_seconds: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )

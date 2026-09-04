"""Evidence domain type — optional domain hint provided alongside a question."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class Evidence(BaseModel):
    """Free-form domain evidence that accompanies an InferenceCase.

    Evidence may contain business-rule hints (e.g. "age > 21 means adult").
    It must never contain gold SQL or gold tables/columns.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str
    """Human-readable hint, e.g. extracted from the BIRD evidence field."""

    metadata: dict[str, Any] = {}
    """Optional structured key-value pairs attached to the hint."""

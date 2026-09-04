"""InferenceCase — the ONLY object a Strategy is allowed to receive.

Gold fields (gold_sql, gold_tables, gold_columns, gold results) are
intentionally absent.  Any attempt to sneak gold into this type
or its dependencies is a leakage violation.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

_FORBIDDEN_EVIDENCE_KEYS = frozenset(
    {
        "gold_sql",
        "gold_tables",
        "gold_columns",
        "gold_result",
        "gold_results",
    }
)


def _reject_gold_evidence(value: Any, path: str = "evidence") -> None:
    if isinstance(value, dict):
        for key, nested_value in value.items():
            if isinstance(key, str) and key.lower() in _FORBIDDEN_EVIDENCE_KEYS:
                raise ValueError(f"{path}.{key} is not allowed in inference evidence")
            _reject_gold_evidence(nested_value, f"{path}.{key}")
    elif isinstance(value, list | tuple):
        for index, nested_value in enumerate(value):
            _reject_gold_evidence(nested_value, f"{path}[{index}]")


class InferenceCase(BaseModel):
    """Immutable inference input: question + context, zero gold."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    """Stable identifier matching the benchmark entry (e.g. BIRD row index)."""

    question: str
    """Natural-language question to answer with SQL."""

    database_id: str
    """Target database identifier (maps to a DatabaseCatalog)."""

    evidence: dict[str, Any] | None = None
    """Optional domain evidence (business-rule hints).  Must not contain gold."""

    @field_validator("evidence")
    @classmethod
    def evidence_must_not_contain_gold(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is not None:
            _reject_gold_evidence(value)
        return value

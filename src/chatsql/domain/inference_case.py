"""InferenceCase — the ONLY object a Strategy is allowed to receive.

Gold fields (gold_sql, gold_tables, gold_columns, gold results) are
intentionally absent.  Any attempt to sneak gold into this type
or its dependencies is a leakage violation.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


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

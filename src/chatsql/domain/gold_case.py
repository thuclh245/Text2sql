"""GoldCase — contains ground-truth annotations.

GoldCase MUST NOT be passed to any Strategy or inference component.
It is only consumed by the Evaluator, which runs after inference completes.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class GoldCase(BaseModel):
    """Immutable gold-standard annotation for a single benchmark item."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    """Must match the corresponding InferenceCase.case_id."""

    gold_sql: str
    """Reference SQL query that answers the question correctly."""

    gold_tables: tuple[str, ...] = ()
    """Tables that the gold query touches (used for table-recall metric)."""

    gold_columns: tuple[str, ...] = ()
    """Columns that the gold query touches (used for column-recall metric)."""

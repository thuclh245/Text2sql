"""Base Evaluator interface for the evaluation layer."""

from __future__ import annotations

import abc
from typing import Any

from chatsql.domain.result import ExecutionResult, Prediction


class BaseEvaluator(abc.ABC):
    """Abstract evaluator — the ONLY component allowed to hold GoldCase data."""

    @abc.abstractmethod
    def evaluate(
        self,
        prediction: Prediction,
        execution: ExecutionResult,
        gold_sql: str,
        gold_tables: tuple[str, ...],
        gold_columns: tuple[str, ...],
    ) -> dict[str, Any]:
        """Return a metric dict for one (prediction, gold) pair."""
        ...

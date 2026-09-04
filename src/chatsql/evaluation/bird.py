"""BIRD-compatible evaluation helpers."""

from __future__ import annotations

from typing import Any

from chatsql.domain.result import ExecutionResult, Prediction
from chatsql.evaluation.base import BaseEvaluator


class BirdEvaluatorAdapter(BaseEvaluator):
    """Evaluate execution accuracy using BIRD's unordered row-set semantics."""

    def __init__(self, gold_results: dict[str, ExecutionResult] | None = None) -> None:
        self.gold_results = gold_results or {}

    def evaluate(
        self,
        prediction: Prediction,
        execution: ExecutionResult,
        gold_sql: str,
        gold_tables: tuple[str, ...],
        gold_columns: tuple[str, ...],
    ) -> dict[str, Any]:
        gold_execution = self.gold_results.get(prediction.case_id)
        if gold_execution is None:
            return {
                "execution_correct": False,
                "evaluator_ready": False,
                "reason": "missing gold execution result",
            }
        return {
            "execution_correct": self.execution_matches(execution, gold_execution),
            "evaluator_ready": True,
        }

    @staticmethod
    def execution_matches(predicted: ExecutionResult, gold: ExecutionResult) -> bool:
        if not predicted.executed or not gold.executed:
            return False
        return _row_set(predicted.rows) == _row_set(gold.rows)


def _row_set(rows: list[list[Any]]) -> set[tuple[Any, ...]]:
    return {tuple(row) for row in rows}

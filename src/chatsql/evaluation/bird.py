"""BIRD EX (Execution Accuracy) evaluator.

Matches the official BIRD ``calculate_ex``: a prediction is correct iff the set
of result rows equals the set of gold result rows.

Both the predicted and the gold SQL run through the *same* executor, so they
share the read-only guard, the timeout, and the row limit - the two sides can
never be compared under different rules.
"""

from __future__ import annotations

from typing import Any

from chatsql.domain.result import ExecutionResult, Prediction
from chatsql.evaluation.base import BaseEvaluator
from chatsql.execution.base import BaseExecutor


def _rows_to_set(rows: list[list[Any]]) -> set[tuple[Any, ...]]:
    return {tuple(row) for row in rows}


class BirdEXEvaluator(BaseEvaluator):
    """Execution Accuracy evaluator for the BIRD SQLite split."""

    def __init__(
        self,
        executor: BaseExecutor,
        case_database_ids: dict[str, str] | None = None,
    ) -> None:
        self.executor = executor
        self.case_database_ids = case_database_ids or {}

    def evaluate(
        self,
        prediction: Prediction,
        execution: ExecutionResult,
        gold_sql: str,
        gold_tables: tuple[str, ...],
        gold_columns: tuple[str, ...],
    ) -> dict[str, Any]:
        """Return the EX metric dict for one (prediction, gold) pair."""
        db_id = self.case_database_ids.get(
            prediction.case_id, prediction.metadata.get("database_id", "")
        )
        gold_execution = self.executor.execute(gold_sql, db_id, prediction.case_id)

        if not gold_execution.executed:
            return _result(
                correct=False,
                gold_executed=False,
                error=f"Gold SQL failed: {gold_execution.error}",
            )
        if not execution.executed:
            return _result(correct=False, gold_executed=True, error=execution.error)
        if execution.truncated or gold_execution.truncated:
            return _result(
                correct=False,
                gold_executed=True,
                error="result set exceeded row_limit; EX is undefined",
            )

        correct = _rows_to_set(execution.rows) == _rows_to_set(gold_execution.rows)
        return _result(
            correct=correct,
            gold_executed=True,
            pred_row_count=len(execution.rows),
            gold_row_count=len(gold_execution.rows),
        )


def _result(
    *,
    correct: bool,
    gold_executed: bool,
    error: str | None = None,
    pred_row_count: int | None = None,
    gold_row_count: int | None = None,
) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "execution_correct": correct,
        "ex_score": 1.0 if correct else 0.0,
        "gold_executed": gold_executed,
    }
    if error is not None:
        metrics["error"] = error
    if pred_row_count is not None:
        metrics["pred_row_count"] = pred_row_count
    if gold_row_count is not None:
        metrics["gold_row_count"] = gold_row_count
    return metrics

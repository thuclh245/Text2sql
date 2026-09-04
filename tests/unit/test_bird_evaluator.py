from __future__ import annotations

from chatsql.domain.result import ExecutionResult, Prediction
from chatsql.evaluation import BirdEvaluatorAdapter


def test_bird_evaluator_matches_rows_as_unordered_set() -> None:
    evaluator = BirdEvaluatorAdapter(
        {
            "case_1": ExecutionResult(
                case_id="case_1",
                executed=True,
                rows=[[1, "Ada"], [2, "Grace"]],
            )
        }
    )

    metrics = evaluator.evaluate(
        prediction=Prediction(case_id="case_1", predicted_sql="SELECT ..."),
        execution=ExecutionResult(
            case_id="case_1",
            executed=True,
            rows=[[2, "Grace"], [1, "Ada"]],
        ),
        gold_sql="SELECT ...",
        gold_tables=(),
        gold_columns=(),
    )

    assert metrics["execution_correct"] is True
    assert metrics["evaluator_ready"] is True


def test_bird_evaluator_reports_missing_gold_execution() -> None:
    evaluator = BirdEvaluatorAdapter()

    metrics = evaluator.evaluate(
        prediction=Prediction(case_id="case_1", predicted_sql="SELECT 1"),
        execution=ExecutionResult(case_id="case_1", executed=True, rows=[[1]]),
        gold_sql="SELECT 1",
        gold_tables=(),
        gold_columns=(),
    )

    assert metrics["execution_correct"] is False
    assert metrics["evaluator_ready"] is False

from __future__ import annotations

import sqlite3
from pathlib import Path

from chatsql.domain.result import ExecutionResult, Prediction
from chatsql.evaluation import BirdEXEvaluator
from chatsql.execution import ReadOnlySQLiteExecutor


def _create_sqlite_db(root: Path) -> None:
    db_dir = root / "shop"
    db_dir.mkdir()
    with sqlite3.connect(db_dir / "shop.sqlite") as conn:
        conn.execute("CREATE TABLE users(id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO users(id, name) VALUES (1, 'Ada'), (2, 'Grace')")


def test_bird_evaluator_matches_rows_as_unordered_set(tmp_path: Path) -> None:
    _create_sqlite_db(tmp_path)
    evaluator = BirdEXEvaluator(
        ReadOnlySQLiteExecutor(tmp_path),
        case_database_ids={"case_1": "shop"},
    )

    metrics = evaluator.evaluate(
        prediction=Prediction(case_id="case_1", predicted_sql="SELECT name FROM users"),
        execution=ExecutionResult(
            case_id="case_1",
            executed=True,
            rows=[["Grace"], ["Ada"]],
        ),
        gold_sql="SELECT name FROM users",
        gold_tables=(),
        gold_columns=(),
    )

    assert metrics["execution_correct"] is True
    assert metrics["gold_executed"] is True


def test_bird_evaluator_reports_missing_database(tmp_path: Path) -> None:
    evaluator = BirdEXEvaluator(
        ReadOnlySQLiteExecutor(tmp_path),
        case_database_ids={"case_1": "missing"},
    )

    metrics = evaluator.evaluate(
        prediction=Prediction(case_id="case_1", predicted_sql="SELECT 1"),
        execution=ExecutionResult(case_id="case_1", executed=True, rows=[[1]]),
        gold_sql="SELECT 1",
        gold_tables=(),
        gold_columns=(),
    )

    assert metrics["execution_correct"] is False
    assert metrics["gold_executed"] is False

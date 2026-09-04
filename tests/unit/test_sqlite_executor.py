from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from chatsql.execution import ReadOnlySQLiteExecutor


def _create_sqlite_db(root: Path) -> None:
    db_dir = root / "shop"
    db_dir.mkdir()
    with sqlite3.connect(db_dir / "shop.sqlite") as conn:
        conn.execute("CREATE TABLE users(id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO users(name) VALUES ('Ada')")


def test_read_only_sqlite_executor_runs_select(tmp_path: Path) -> None:
    _create_sqlite_db(tmp_path)
    executor = ReadOnlySQLiteExecutor(tmp_path)

    result = executor.execute("SELECT name FROM users", database_id="shop", case_id="case_1")

    assert result.executed is True
    assert result.rows == [["Ada"]]


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE users",
        "/* comment */ DROP TABLE users",
        "WITH removed AS (DELETE FROM users RETURNING id) SELECT * FROM removed",
    ],
)
def test_read_only_sqlite_executor_rejects_writes(tmp_path: Path, sql: str) -> None:
    _create_sqlite_db(tmp_path)
    executor = ReadOnlySQLiteExecutor(tmp_path)

    result = executor.execute(sql, database_id="shop", case_id="case_1")

    assert result.executed is False
    assert result.error is not None


def test_read_only_sqlite_executor_reports_missing_db(tmp_path: Path) -> None:
    executor = ReadOnlySQLiteExecutor(tmp_path)

    result = executor.execute("SELECT 1", database_id="missing", case_id="case_1")

    assert result.executed is False
    assert "Database file not found" in str(result.error)

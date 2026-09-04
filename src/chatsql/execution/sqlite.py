"""Read-only SQLite executor with timeout and DML/DDL guard.

Requirements :
  - read-only: open DB with `?mode=ro` URI flag
  - timeout: hard limit via threading
  - structured execution errors
  - rejects all write statements (DDL/DML)
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

import sqlglot
from sqlglot import exp

from chatsql.domain.result import ExecutionResult
from chatsql.execution.base import BaseExecutor

_FORBIDDEN_EXPRESSIONS = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.Command,
)


class ReadOnlySQLiteExecutor(BaseExecutor):
    """Executes SELECT queries against a SQLite database in read-only mode."""

    def __init__(
        self,
        db_root: Path,
        timeout_seconds: float = 30.0,
        max_rows: int = 10_000,
    ) -> None:
        self.db_root = db_root
        self.timeout_seconds = timeout_seconds
        self.max_rows = max_rows

    def execute(self, sql: str, database_id: str, case_id: str) -> ExecutionResult:
        """Execute SQL and return an ExecutionResult."""
        # 1. Static guard: reject forbidden statements
        guard_error = self._check_write_guard(sql)
        if guard_error:
            return ExecutionResult(
                case_id=case_id,
                executed=False,
                error=guard_error,
            )

        # 2. Resolve DB path
        db_path = self.db_root / database_id / f"{database_id}.sqlite"
        if not db_path.exists():
            return ExecutionResult(
                case_id=case_id,
                executed=False,
                error=f"Database file not found: {db_path}",
            )

        # 3. Execute with timeout
        result_container: dict[str, Any] = {}
        start = time.monotonic()
        thread = threading.Thread(
            target=self._run_query,
            args=(sql, db_path, result_container),
            daemon=True,
        )
        thread.start()
        thread.join(timeout=self.timeout_seconds)
        elapsed = time.monotonic() - start

        if thread.is_alive():
            return ExecutionResult(
                case_id=case_id,
                executed=False,
                error=f"Execution timed out after {self.timeout_seconds:.1f}s",
                execution_time_seconds=elapsed,
            )

        if "error" in result_container:
            return ExecutionResult(
                case_id=case_id,
                executed=False,
                error=result_container["error"],
                execution_time_seconds=elapsed,
            )

        rows: list[list[Any]] = result_container.get("rows", [])
        if len(rows) > self.max_rows:
            rows = rows[: self.max_rows]

        return ExecutionResult(
            case_id=case_id,
            executed=True,
            rows=rows,
            execution_time_seconds=elapsed,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _run_query(
        self,
        sql: str,
        db_path: Path,
        result: dict[str, Any],
    ) -> None:
        """Run the query in a thread; write rows or error into `result`."""
        try:
            uri = f"file:{db_path}?mode=ro"
            with sqlite3.connect(uri, uri=True) as conn:
                conn.execute("PRAGMA query_only = ON")
                cur = conn.cursor()
                cur.execute(sql)
                rows = [list(row) for row in cur.fetchall()]
            result["rows"] = rows
        except Exception as exc:
            result["error"] = str(exc)

    @staticmethod
    def _check_write_guard(sql: str) -> str | None:
        """Return an error string if the SQL contains forbidden operations."""
        try:
            parsed = sqlglot.parse_one(sql, read="sqlite")
        except sqlglot.errors.ParseError as exc:
            return f"SQL parse error: {exc}"
        if parsed is None:
            return "SQL parse error: empty statement"
        if not isinstance(parsed, exp.Query):
            return "Write/DDL statement rejected by read-only guard"
        for expression_type in _FORBIDDEN_EXPRESSIONS:
            if parsed.find(expression_type):
                return "Write/DDL statement rejected by read-only guard"
        return None

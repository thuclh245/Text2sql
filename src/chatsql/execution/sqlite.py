"""Read-only SQLite executor with a hard timeout and a write/DDL guard.

Guarantees:
  - the database is opened ``mode=ro`` and ``PRAGMA query_only = ON``;
  - only a single read-only query runs (see ``execution.guard``);
  - a query that overruns ``timeout_seconds`` is interrupted, not left running;
  - every failure is reported as a structured ``ExecutionResult`` with an
    ``error_kind`` the caller can aggregate on.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path
from typing import Any

from chatsql.domain.result import ExecutionResult
from chatsql.execution.base import BaseExecutor
from chatsql.execution.guard import inspect_read_only

_INTERRUPT_GRACE_SECONDS = 5.0


class ReadOnlySQLiteExecutor(BaseExecutor):
    """Executes a single SELECT against ``<db_root>/<database_id>/<database_id>.sqlite``."""

    def __init__(
        self,
        db_root: Path,
        timeout_seconds: float = 30.0,
        row_limit: int = 10_000,
    ) -> None:
        self.db_root = db_root
        self.timeout_seconds = timeout_seconds
        self.row_limit = row_limit

    def execute(self, sql: str, database_id: str, case_id: str) -> ExecutionResult:
        verdict = inspect_read_only(sql)
        if not verdict.ok:
            return ExecutionResult(
                case_id=case_id,
                executed=False,
                error=verdict.reason,
                error_kind="invalid_sql" if verdict.is_parse_error else "rejected",
            )

        db_path = self.db_root / database_id / f"{database_id}.sqlite"
        if not db_path.exists():
            return ExecutionResult(
                case_id=case_id,
                executed=False,
                error=f"Database file not found: {db_path}",
                error_kind="missing_db",
            )

        container: dict[str, Any] = {}
        connection_box: dict[str, sqlite3.Connection] = {}
        start = time.monotonic()
        thread = threading.Thread(
            target=self._run_query,
            args=(sql, db_path, container, connection_box),
            daemon=True,
        )
        thread.start()
        thread.join(timeout=self.timeout_seconds)

        if thread.is_alive():
            connection = connection_box.get("connection")
            if connection is not None:
                connection.interrupt()
            thread.join(timeout=_INTERRUPT_GRACE_SECONDS)
            return ExecutionResult(
                case_id=case_id,
                executed=False,
                error=f"Execution timed out after {self.timeout_seconds:.1f}s",
                error_kind="timeout",
                execution_time_seconds=time.monotonic() - start,
            )

        elapsed = time.monotonic() - start
        if "error" in container:
            return ExecutionResult(
                case_id=case_id,
                executed=False,
                error=container["error"],
                error_kind="runtime_error",
                execution_time_seconds=elapsed,
            )

        rows: list[list[Any]] = container.get("rows", [])
        row_count = len(rows)
        truncated = row_count > self.row_limit
        if truncated:
            rows = rows[: self.row_limit]

        return ExecutionResult(
            case_id=case_id,
            executed=True,
            rows=rows,
            row_count=row_count,
            truncated=truncated,
            execution_time_seconds=elapsed,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _run_query(
        sql: str,
        db_path: Path,
        result: dict[str, Any],
        connection_box: dict[str, sqlite3.Connection],
    ) -> None:
        """Run the query in a worker thread; publish rows or an error string."""
        try:
            uri = f"file:{db_path}?mode=ro"
            with closing(sqlite3.connect(uri, uri=True)) as conn:
                connection_box["connection"] = conn
                conn.execute("PRAGMA query_only = ON")
                cursor = conn.cursor()
                cursor.execute(sql)
                result["rows"] = [list(row) for row in cursor.fetchall()]
        except Exception as exc:  # noqa: BLE001 - surfaced as a structured error
            result["error"] = str(exc)

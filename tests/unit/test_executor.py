"""Tests for read-only SQLite execution."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from chatsql.execution.sqlite import ReadOnlySQLiteExecutor

# ---------------------------------------------------------------------------
# Fixture: a real in-memory SQLite DB file
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_root(tmp_path: Path) -> Path:
    """Create a minimal SQLite DB under tmp/shop/shop.sqlite."""
    db_dir = tmp_path / "shop"
    db_dir.mkdir()
    db_path = db_dir / "shop.sqlite"

    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT, price REAL)")
    conn.execute("INSERT INTO products VALUES (1, 'Widget', 9.99)")
    conn.execute("INSERT INTO products VALUES (2, 'Gadget', 19.99)")
    conn.commit()
    conn.close()
    return tmp_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestReadOnlySQLiteExecutor:
    def test_select_returns_rows(self, db_root: Path) -> None:
        exc = ReadOnlySQLiteExecutor(db_root=db_root)
        result = exc.execute("SELECT * FROM products", "shop", "q1")
        assert result.executed is True
        assert len(result.rows) == 2

    def test_select_count(self, db_root: Path) -> None:
        exc = ReadOnlySQLiteExecutor(db_root=db_root)
        result = exc.execute("SELECT COUNT(*) FROM products", "shop", "q2")
        assert result.executed is True
        assert result.rows == [[2]]

    def test_missing_db_returns_error(self, db_root: Path) -> None:
        exc = ReadOnlySQLiteExecutor(db_root=db_root)
        result = exc.execute("SELECT 1", "nonexistent_db", "q3")
        assert result.executed is False
        assert result.error is not None

    def test_syntax_error_returns_error(self, db_root: Path) -> None:
        exc = ReadOnlySQLiteExecutor(db_root=db_root)
        result = exc.execute("SELEKT * FORM products", "shop", "q4")
        assert result.executed is False
        assert result.error is not None

    def test_insert_rejected(self, db_root: Path) -> None:
        exc = ReadOnlySQLiteExecutor(db_root=db_root)
        result = exc.execute("INSERT INTO products VALUES (3, 'Bad', 0.0)", "shop", "q5")
        assert result.executed is False
        assert "rejected" in (result.error or "").lower()

    def test_drop_rejected(self, db_root: Path) -> None:
        exc = ReadOnlySQLiteExecutor(db_root=db_root)
        result = exc.execute("DROP TABLE products", "shop", "q6")
        assert result.executed is False

    def test_create_rejected(self, db_root: Path) -> None:
        exc = ReadOnlySQLiteExecutor(db_root=db_root)
        result = exc.execute("CREATE TABLE t2 (id INTEGER)", "shop", "q7")
        assert result.executed is False

    def test_update_rejected(self, db_root: Path) -> None:
        exc = ReadOnlySQLiteExecutor(db_root=db_root)
        result = exc.execute("UPDATE products SET price = 0 WHERE id = 1", "shop", "q8")
        assert result.executed is False

    def test_execution_time_recorded(self, db_root: Path) -> None:
        exc = ReadOnlySQLiteExecutor(db_root=db_root)
        result = exc.execute("SELECT 1", "shop", "q9")
        assert result.execution_time_seconds is not None
        assert result.execution_time_seconds >= 0

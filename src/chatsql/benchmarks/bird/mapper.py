"""Schema mapper: BIRD SQLite schema DDL → DatabaseCatalog.

BIRD does not ship a structured schema JSON — instead each record contains
a 'schema' field with CREATE TABLE DDL (in the prompt JSONL).
For the main question JSON + the actual .sqlite file, we parse the schema
by introspecting the live SQLite database via PRAGMA queries.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from chatsql.domain.catalog import ColumnInfo, DatabaseCatalog, TableInfo


class BirdSchemaMapper:
    """Builds a DatabaseCatalog from a SQLite database file via PRAGMA."""

    def load(self, db_path: Path) -> DatabaseCatalog:
        """Introspect a SQLite .sqlite file and return a DatabaseCatalog."""
        if not db_path.exists():
            raise FileNotFoundError(f"SQLite DB not found: {db_path}")

        database_id = db_path.stem  # filename without extension
        tables: list[TableInfo] = []

        with closing(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            # Get all user tables
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
            table_names = [row["name"] for row in cur.fetchall()]

            # Collect FK targets for annotation
            fk_map = self._build_fk_map(conn, table_names)

            for tname in table_names:
                columns = self._load_columns(conn, tname, fk_map)
                tables.append(TableInfo(name=tname, columns=tuple(columns)))

        return DatabaseCatalog(database_id=database_id, tables=tuple(tables))

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        escaped = identifier.replace('"', '""')
        return f'"{escaped}"'

    @staticmethod
    def _load_columns(
        conn: sqlite3.Connection,
        table_name: str,
        fk_map: dict[tuple[str, str], str],
    ) -> list[ColumnInfo]:
        """Use PRAGMA table_info to get columns."""
        cur = conn.cursor()
        cur.execute(f"PRAGMA table_info({BirdSchemaMapper._quote_identifier(table_name)})")
        rows = cur.fetchall()

        columns: list[ColumnInfo] = []
        for row in rows:
            col_name: str = row[1]
            col_type: str = row[2] or "TEXT"
            is_pk: bool = bool(row[5])  # pk column (1 = primary key)

            fk_ref = fk_map.get((table_name, col_name))
            is_fk = fk_ref is not None

            columns.append(
                ColumnInfo(
                    name=col_name,
                    data_type=col_type,
                    is_primary_key=is_pk,
                    is_foreign_key=is_fk,
                    references=fk_ref,
                )
            )
        return columns

    @staticmethod
    def _build_fk_map(
        conn: sqlite3.Connection,
        table_names: list[str],
    ) -> dict[tuple[str, str], str]:
        """Return {(table, column): 'ref_table.ref_column'} for all FKs."""
        fk_map: dict[tuple[str, str], str] = {}
        cur = conn.cursor()
        for tname in table_names:
            cur.execute(f"PRAGMA foreign_key_list({BirdSchemaMapper._quote_identifier(tname)})")
            for row in cur.fetchall():
                # row: (id, seq, table, from, to, on_update, on_delete, match)
                from_col: str = row[3]
                to_table: str = row[2]
                to_col: str = row[4]
                fk_map[(tname, from_col)] = f"{to_table}.{to_col}"
        return fk_map


def load_catalogs(db_root: Path, db_ids: list[str]) -> tuple[dict[str, DatabaseCatalog], list[str]]:
    """Load catalogs for ``db_ids`` from ``db_root/<db_id>/<db_id>.sqlite``.

    Returns ``(catalogs, failures)`` - one ``"<db_id>: <reason>"`` string per
    database that could not be introspected - so a caller can abort before
    spending an LLM budget instead of crashing mid-run.
    """
    mapper = BirdSchemaMapper()
    catalogs: dict[str, DatabaseCatalog] = {}
    failures: list[str] = []
    for db_id in db_ids:
        sqlite_path = db_root / db_id / f"{db_id}.sqlite"
        try:
            catalogs[db_id] = mapper.load(sqlite_path)
        except Exception as exc:  # noqa: BLE001 - reported, not raised
            failures.append(f"{db_id}: {exc}")
    return catalogs, failures

"""Catalog domain types — read-only schema metadata passed to strategies."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ColumnInfo(BaseModel):
    """Metadata for a single table column."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    data_type: str
    is_primary_key: bool = False
    is_foreign_key: bool = False
    references: str | None = None
    """'table.column' reference target if is_foreign_key."""
    description: str | None = None


class TableInfo(BaseModel):
    """Metadata for a single database table."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    columns: tuple[ColumnInfo, ...] = ()
    description: str | None = None

    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]


class DatabaseCatalog(BaseModel):
    """Read-only schema metadata for one database.

    Passed to strategies.  Must not contain gold SQL or gold labels.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    database_id: str
    tables: tuple[TableInfo, ...] = ()

    def table_names(self) -> list[str]:
        return [t.name for t in self.tables]

    def get_table(self, name: str) -> TableInfo | None:
        for t in self.tables:
            if t.name == name:
                return t
        return None

    @classmethod
    def from_dict(cls, data: dict) -> DatabaseCatalog:  # type: ignore[type-arg]
        """Convenience constructor from a plain dict (e.g. loaded from JSON)."""
        tables: list[TableInfo] = []
        for t in data.get("tables", []):
            cols = [ColumnInfo(**c) for c in t.get("columns", [])]
            tables.append(
                TableInfo(
                    name=t["name"],
                    columns=tuple(cols),
                    description=t.get("description"),
                )
            )
        return cls(database_id=data["database_id"], tables=tuple(tables))

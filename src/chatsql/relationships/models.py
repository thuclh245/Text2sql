"""Domain models for Phase 6B relationship, join-path, and grain reasoning."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Cardinality(StrEnum):
    """Cardinality relationship between two tables."""

    ONE_TO_ONE = "ONE_TO_ONE"
    ONE_TO_MANY = "ONE_TO_MANY"
    MANY_TO_ONE = "MANY_TO_ONE"
    MANY_TO_MANY = "MANY_TO_MANY"


class RelationType(StrEnum):
    """Origin/type of relationship edge."""

    FOREIGN_KEY = "FOREIGN_KEY"
    IMPLICIT = "IMPLICIT"
    INFERRED = "INFERRED"


class RelationshipEdge(BaseModel):
    """Directed or undirected relational connection between two tables."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    left_table: str
    right_table: str
    left_columns: tuple[str, ...]
    right_columns: tuple[str, ...]
    relation_type: str = RelationType.FOREIGN_KEY.value
    cardinality: str | None = None
    provenance: str = "declared_fk"
    confidence: float | None = 1.0

    def involves(self, table: str) -> bool:
        """Return True if the edge touches the specified table."""
        return self.left_table == table or self.right_table == table

    def other_table(self, table: str) -> str:
        """Return the other endpoint of the edge."""
        if self.left_table == table:
            return self.right_table
        if self.right_table == table:
            return self.left_table
        raise ValueError(f"Table {table!r} is not an endpoint of this edge")

    def canonical_pair(self) -> tuple[str, str]:
        """Return table endpoints in sorted order for undirected comparisons."""
        return tuple(sorted((self.left_table, self.right_table)))  # type: ignore[return-value]


class RelationshipPlan(BaseModel):
    """Selected join graph, aggregation grain, and evidence for a query."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tables: tuple[str, ...]
    edges: tuple[RelationshipEdge, ...]
    grain: tuple[str, ...] = Field(default_factory=tuple)
    evidence: tuple[dict[str, Any], ...] = Field(default_factory=tuple)
    confidence: float | None = 1.0

    @property
    def is_single_table(self) -> bool:
        """True if the plan does not require multi-table joins."""
        return len(self.tables) <= 1

    @property
    def hop_count(self) -> int:
        """Number of join hops in the plan."""
        return len(self.edges)

    def summary(self) -> str:
        """Human-readable summary of tables and join edges."""
        if not self.edges:
            return f"Tables: {', '.join(self.tables)} (no joins)"
        edge_strs = [
            (
                f"{e.left_table}.{','.join(e.left_columns)} = "
                f"{e.right_table}.{','.join(e.right_columns)}"
            )
            for e in self.edges
        ]
        return f"Tables: {', '.join(self.tables)} | Joins: {' AND '.join(edge_strs)}"

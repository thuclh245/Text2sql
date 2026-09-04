"""Base interfaces and data structures for Schema Grounding (Retrieval).

Defines SchemaGrounder protocol and GroundingResult container.
Rule: Zero Gold Leakage — ground() receives InferenceCase + DatabaseCatalog ONLY.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any

from chatsql.domain.catalog import DatabaseCatalog
from chatsql.domain.inference_case import InferenceCase


@dataclass(frozen=True)
class TableRef:
    """Reference to a table in the database schema."""

    name: str


@dataclass(frozen=True)
class ColumnRef:
    """Reference to a column in a database table."""

    table_name: str
    column_name: str


@dataclass
class GroundingResult:
    """Output of a SchemaGrounder containing selected schema elements and scores."""

    tables: tuple[TableRef, ...]
    columns: tuple[ColumnRef, ...]
    evidence: tuple[dict[str, Any], ...] = ()
    scores: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def table_names(self) -> set[str]:
        """Set of selected table names."""
        return {t.name for t in self.tables}

    @property
    def column_names(self) -> set[tuple[str, str]]:
        """Set of selected (table_name, column_name) pairs."""
        return {(c.table_name, c.column_name) for c in self.columns}


class SchemaGrounder(abc.ABC):
    """Abstract interface for all Schema Grounders (retrievers)."""

    @abc.abstractmethod
    def ground(self, case: InferenceCase, catalog: DatabaseCatalog) -> GroundingResult:
        """Ground the inference case against the catalog to produce a GroundingResult."""
        ...

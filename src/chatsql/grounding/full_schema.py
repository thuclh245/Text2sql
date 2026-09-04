"""FullSchemaGrounder implementation.

Returns all tables and columns from the DatabaseCatalog (Zero Filtering).
Used as the default grounder for B0 Full-Schema baseline experiments.
"""

from __future__ import annotations

from typing import Any

from chatsql.domain.catalog import DatabaseCatalog
from chatsql.domain.inference_case import InferenceCase
from chatsql.grounding.base import ColumnRef, GroundingResult, SchemaGrounder, TableRef
from chatsql.grounding.registry import register_grounder


@register_grounder("full-schema")
class FullSchemaGrounder(SchemaGrounder):
    """Grounder that retains all tables and columns in the database catalog."""

    def ground(self, case: InferenceCase, catalog: DatabaseCatalog) -> GroundingResult:
        tables: list[TableRef] = []
        columns: list[ColumnRef] = []

        for table in catalog.tables:
            tables.append(TableRef(name=table.name))
            for col in table.columns:
                columns.append(ColumnRef(table_name=table.name, column_name=col.name))

        evidence_tuple: tuple[dict[str, Any], ...] = ()
        if case.evidence:
            evidence_tuple = (case.evidence,)

        return GroundingResult(
            tables=tuple(tables),
            columns=tuple(columns),
            evidence=evidence_tuple,
            scores={"full_schema": 1.0},
            metadata={"grounder": "full-schema", "total_tables": len(tables)},
        )

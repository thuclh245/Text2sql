"""LitE-SQL Grounder Adapter.

Adapts LitE-SQL schema retriever component into the CHATSQL SchemaGrounder interface.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from chatsql.baselines.lite_sql.input_mapper import LiteSqlInputMapper
from chatsql.domain.catalog import DatabaseCatalog
from chatsql.domain.inference_case import InferenceCase
from chatsql.grounding.base import ColumnRef, GroundingResult, SchemaGrounder, TableRef
from chatsql.grounding.registry import register_grounder


@register_grounder("lite-sql")
class LitESQLGrounderAdapter(SchemaGrounder):
    """Adapter wrapping LitE-SQL retriever under the SchemaGrounder protocol."""

    def __init__(
        self,
        top_k_tables: int = 5,
        retriever: Callable[[dict[str, Any]], Sequence[str]] | None = None,
    ) -> None:
        self.top_k_tables = top_k_tables
        self.input_mapper = LiteSqlInputMapper()
        self._retriever = retriever

    def ground(self, case: InferenceCase, catalog: DatabaseCatalog) -> GroundingResult:
        if self._retriever is None:
            raise NotImplementedError(
                "LitE-SQL grounder requires an upstream retriever; "
                "use simple-dense for the local baseline."
            )

        lite_input = self.input_mapper.to_lite_sql_format(case, catalog)
        selected_names = set(self._retriever(lite_input)[: self.top_k_tables])

        tables: list[TableRef] = []
        columns: list[ColumnRef] = []

        for tbl in catalog.tables:
            if tbl.name not in selected_names:
                continue
            tables.append(TableRef(name=tbl.name))
            for col in tbl.columns:
                columns.append(ColumnRef(table_name=tbl.name, column_name=col.name))

        return GroundingResult(
            tables=tuple(tables),
            columns=tuple(columns),
            evidence=(case.evidence,) if case.evidence else (),
            scores={"lite_sql_retrieval_score": 1.0},
            metadata={
                "grounder": "lite-sql",
                "top_k_tables": self.top_k_tables,
                "retrieved_tables_count": len(tables),
            },
        )

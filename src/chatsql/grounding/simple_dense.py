"""SimpleDenseGrounder implementation.

Lightweight keyword and similarity-based schema retriever for baseline comparison.
Ranks tables and columns by token overlap with the question and evidence text.
"""

from __future__ import annotations

import re

from chatsql.domain.catalog import DatabaseCatalog
from chatsql.domain.inference_case import InferenceCase
from chatsql.grounding.base import ColumnRef, GroundingResult, SchemaGrounder, TableRef
from chatsql.grounding.registry import register_grounder


def _tokenize(text: str) -> set[str]:
    """Tokenize string into normalized lowercase alphanumeric words."""
    words = re.findall(r"\w+", text.lower())
    return {w for w in words if len(w) > 1}


@register_grounder("simple-dense")
class SimpleDenseGrounder(SchemaGrounder):
    """Simple term-overlap schema grounder."""

    def __init__(self, top_k_tables: int = 5, top_k_columns: int = 20) -> None:
        self.top_k_tables = top_k_tables
        self.top_k_columns = top_k_columns

    def ground(self, case: InferenceCase, catalog: DatabaseCatalog) -> GroundingResult:
        query_text = case.question
        if case.evidence:
            query_text += " " + str(case.evidence.get("text", ""))

        query_tokens = _tokenize(query_text)

        table_scores: list[tuple[float, str]] = []
        col_scores: list[tuple[float, str, str]] = []

        for table in catalog.tables:
            tbl_tokens = _tokenize(table.name)
            tbl_overlap = len(query_tokens & tbl_tokens)
            score = float(tbl_overlap)

            # Bonus score if column names match question
            for col in table.columns:
                col_tokens = _tokenize(col.name)
                col_overlap = len(query_tokens & col_tokens)
                if col_overlap > 0:
                    score += 0.5 * col_overlap
                col_scores.append((float(col_overlap), table.name, col.name))

            table_scores.append((score, table.name))

        # Sort descending by score
        table_scores.sort(key=lambda x: x[0], reverse=True)
        col_scores.sort(key=lambda x: x[0], reverse=True)

        # Select Top-K tables (or all if fewer than top_k)
        selected_tables = {t_name for _, t_name in table_scores[: self.top_k_tables]}
        if not selected_tables and catalog.tables:
            selected_tables = {catalog.tables[0].name}

        table_refs = tuple(TableRef(name=t) for t in sorted(selected_tables))

        selected_columns: set[tuple[str, str]] = set()
        for _, table_name, column_name in col_scores:
            if table_name not in selected_tables:
                continue
            selected_columns.add((table_name, column_name))
            if len(selected_columns) >= self.top_k_columns:
                break

        col_refs: list[ColumnRef] = []
        for _, table_name, column_name in col_scores:
            if (table_name, column_name) in selected_columns:
                col_refs.append(ColumnRef(table_name=table_name, column_name=column_name))

        scores_dict = {f"table_{t}": s for s, t in table_scores if t in selected_tables}

        return GroundingResult(
            tables=table_refs,
            columns=tuple(col_refs),
            evidence=(case.evidence,) if case.evidence else (),
            scores=scores_dict,
            metadata={
                "grounder": "simple-dense",
                "top_k_tables": self.top_k_tables,
                "top_k_columns": self.top_k_columns,
                "retrieved_tables_count": len(table_refs),
                "retrieved_columns_count": len(col_refs),
            },
        )

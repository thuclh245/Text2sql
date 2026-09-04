"""Relationship-aware schema grounder for Phase 6 P6A research."""

from __future__ import annotations

import re
from typing import Any

from chatsql.domain.catalog import ColumnInfo, DatabaseCatalog, TableInfo
from chatsql.domain.inference_case import InferenceCase
from chatsql.grounding.base import ColumnRef, GroundingResult, SchemaGrounder, TableRef
from chatsql.grounding.registry import register_grounder
from chatsql.grounding.schema_graph import build_relationship_graph, expand_fk_neighbors


def _tokenize(text: str | None) -> set[str]:
    if not text:
        return set()
    return {word for word in re.findall(r"\w+", text.lower()) if len(word) > 1}


def _evidence_text(evidence: dict[str, Any] | None) -> str:
    if not evidence:
        return ""
    values: list[str] = []
    for value in evidence.values():
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, int | float | bool):
            values.append(str(value))
    return " ".join(values)


def _score_column(query_tokens: set[str], table: TableInfo, column: ColumnInfo) -> float:
    score = 0.0
    score += 2.0 * len(query_tokens & _tokenize(column.name))
    score += 0.5 * len(query_tokens & _tokenize(column.description))
    score += 0.25 * len(query_tokens & _tokenize(table.name))
    if column.is_primary_key:
        score += 1.0
    if column.is_foreign_key:
        score += 1.5
    return score


def _score_table(query_tokens: set[str], table: TableInfo) -> float:
    score = 0.0
    score += 3.0 * len(query_tokens & _tokenize(table.name))
    score += 1.0 * len(query_tokens & _tokenize(table.description))
    for column in table.columns:
        score += 0.75 * len(query_tokens & _tokenize(column.name))
        score += 0.25 * len(query_tokens & _tokenize(column.description))
    return score


@register_grounder("relationship-aware")
class RelationshipAwareGrounder(SchemaGrounder):
    """Lexical schema ranker with foreign-key neighbor expansion."""

    def __init__(
        self,
        top_k_tables: int = 5,
        top_k_columns: int = 30,
        bridge_closure_depth: int = 1,
        include_fk_neighbors: bool = True,
    ) -> None:
        self.top_k_tables = top_k_tables
        self.top_k_columns = top_k_columns
        self.bridge_closure_depth = bridge_closure_depth
        self.include_fk_neighbors = include_fk_neighbors

    def ground(self, case: InferenceCase, catalog: DatabaseCatalog) -> GroundingResult:
        if not catalog.tables:
            return GroundingResult(
                tables=(),
                columns=(),
                evidence=(case.evidence,) if case.evidence else (),
                scores={},
                metadata=self._metadata({}, [], [], catalog, 0),
            )

        query_tokens = _tokenize(f"{case.question} {_evidence_text(case.evidence)}")
        table_scores = {
            table.name: _score_table(query_tokens, table) for table in catalog.tables
        }
        ranked_tables = sorted(
            catalog.tables,
            key=lambda table: (-table_scores[table.name], table.name),
        )
        seed_limit = max(1, self.top_k_tables)
        seed_tables = {table.name for table in ranked_tables[:seed_limit]}

        graph = build_relationship_graph(catalog)
        selected_table_names = expand_fk_neighbors(
            seed_tables=seed_tables,
            graph=graph,
            depth=self.bridge_closure_depth,
            include_fk_neighbors=self.include_fk_neighbors,
        )
        selected_tables = [
            table for table in catalog.tables if table.name in selected_table_names
        ]
        bridge_tables = sorted(selected_table_names - seed_tables)

        selected_columns = self._select_columns(query_tokens, selected_tables)
        column_refs = tuple(
            ColumnRef(table_name=table.name, column_name=column.name)
            for table, column, _ in selected_columns
        )
        selected_column_scores = {
            f"{table.name}.{column.name}": score for table, column, score in selected_columns
        }

        return GroundingResult(
            tables=tuple(TableRef(name=table.name) for table in selected_tables),
            columns=column_refs,
            evidence=(case.evidence,) if case.evidence else (),
            scores={f"table_{name}": score for name, score in sorted(table_scores.items())},
            metadata=self._metadata(
                table_scores,
                sorted(seed_tables),
                bridge_tables,
                catalog,
                len(column_refs),
                selected_column_scores,
            ),
        )

    def _select_columns(
        self,
        query_tokens: set[str],
        selected_tables: list[TableInfo],
    ) -> list[tuple[TableInfo, ColumnInfo, float]]:
        column_scores: list[tuple[TableInfo, ColumnInfo, float]] = []
        for table in selected_tables:
            for column in table.columns:
                column_scores.append((table, column, _score_column(query_tokens, table, column)))

        if self.top_k_columns <= 0:
            return []

        column_scores.sort(
            key=lambda item: (
                -item[2],
                not item[1].is_primary_key,
                not item[1].is_foreign_key,
                item[0].name,
                item[1].name,
            )
        )
        return column_scores[: self.top_k_columns]

    def _metadata(
        self,
        table_scores: dict[str, float],
        seed_tables: list[str],
        bridge_tables: list[str],
        catalog: DatabaseCatalog,
        selected_column_count: int,
        selected_column_scores: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        catalog_column_count = sum(len(table.columns) for table in catalog.tables)
        selected_table_count = len(set(seed_tables) | set(bridge_tables))
        catalog_table_count = len(catalog.tables)
        return {
            "grounder": "relationship-aware",
            "top_k_tables": self.top_k_tables,
            "top_k_columns": self.top_k_columns,
            "bridge_closure_depth": self.bridge_closure_depth,
            "include_fk_neighbors": self.include_fk_neighbors,
            "seed_tables": seed_tables,
            "bridge_tables": bridge_tables,
            "selected_table_count": selected_table_count,
            "selected_column_count": selected_column_count,
            "catalog_table_count": catalog_table_count,
            "catalog_column_count": catalog_column_count,
            "table_reduction_ratio": _reduction_ratio(
                selected_table_count, catalog_table_count
            ),
            "column_reduction_ratio": _reduction_ratio(
                selected_column_count, catalog_column_count
            ),
            "table_scores": {name: round(score, 4) for name, score in table_scores.items()},
            "column_scores": {
                name: round(score, 4)
                for name, score in (selected_column_scores or {}).items()
            },
        }


def _reduction_ratio(selected_count: int, total_count: int) -> float:
    if total_count <= 0:
        return 0.0
    return round(1.0 - (selected_count / total_count), 4)

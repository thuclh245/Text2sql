"""Relationship-aware schema grounder for grounding retrieval research."""

from __future__ import annotations

from typing import Any

from chatsql.domain.catalog import ColumnInfo, DatabaseCatalog, TableInfo
from chatsql.domain.inference_case import InferenceCase
from chatsql.grounding.base import ColumnRef, GroundingResult, SchemaGrounder, TableRef
from chatsql.grounding.registry import register_grounder
from chatsql.grounding.schema_graph import (
    RelationshipGraph,
    build_relationship_graph,
    expand_fk_neighbors,
    relationship_edges,
)
from chatsql.text_utils import tokenize as _tokenize


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
        include_key_columns: bool = True,
    ) -> None:
        self.top_k_tables = top_k_tables
        self.top_k_columns = top_k_columns
        self.bridge_closure_depth = bridge_closure_depth
        self.include_fk_neighbors = include_fk_neighbors
        self.include_key_columns = include_key_columns

    def ground(self, case: InferenceCase, catalog: DatabaseCatalog) -> GroundingResult:
        if not catalog.tables:
            return GroundingResult(
                tables=(),
                columns=(),
                evidence=(case.evidence,) if case.evidence else (),
                scores={},
                metadata=self._metadata({}, [], [], catalog, 0, {}),
            )

        query_tokens = _tokenize(f"{case.question} {_evidence_text(case.evidence)}")
        table_scores = {table.name: _score_table(query_tokens, table) for table in catalog.tables}
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
        selected_tables = [table for table in catalog.tables if table.name in selected_table_names]
        bridge_tables = sorted(selected_table_names - seed_tables)

        selected_columns = self._select_columns(query_tokens, selected_tables, graph)
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
                graph,
                selected_column_scores,
            ),
        )

    def _select_columns(
        self,
        query_tokens: set[str],
        selected_tables: list[TableInfo],
        graph: RelationshipGraph,
    ) -> list[tuple[TableInfo, ColumnInfo, float]]:
        column_scores: list[tuple[TableInfo, ColumnInfo, float]] = []
        for table in selected_tables:
            for column in table.columns:
                column_scores.append((table, column, _score_column(query_tokens, table, column)))

        pinned_columns = self._key_columns_for_selected_relationships(selected_tables, graph)
        if self.top_k_columns <= 0:
            return [
                item for item in column_scores if (item[0].name, item[1].name) in pinned_columns
            ]

        column_scores.sort(
            key=lambda item: (
                -item[2],
                not item[1].is_primary_key,
                not item[1].is_foreign_key,
                item[0].name,
                item[1].name,
            )
        )
        selected = column_scores[: self.top_k_columns]
        selected_names = {(table.name, column.name) for table, column, _ in selected}
        for item in column_scores:
            name = (item[0].name, item[1].name)
            if name in pinned_columns and name not in selected_names:
                selected.append(item)
                selected_names.add(name)
        return selected

    def _key_columns_for_selected_relationships(
        self,
        selected_tables: list[TableInfo],
        graph: RelationshipGraph,
    ) -> set[tuple[str, str]]:
        if not self.include_key_columns:
            return set()

        selected_table_names = {table.name for table in selected_tables}
        selected_relationship_tables = {
            table_name
            for table_name in selected_table_names
            if graph.get(table_name, set()) & selected_table_names
        }
        pinned: set[tuple[str, str]] = set()

        for table in selected_tables:
            if table.name not in selected_relationship_tables:
                continue
            for column in table.columns:
                if column.is_primary_key:
                    pinned.add((table.name, column.name))
                    continue
                if not column.is_foreign_key or not column.references:
                    continue
                target_table = _reference_table_name(column.references)
                if target_table in selected_table_names:
                    pinned.add((table.name, column.name))

        return pinned

    def _metadata(
        self,
        table_scores: dict[str, float],
        seed_tables: list[str],
        bridge_tables: list[str],
        catalog: DatabaseCatalog,
        selected_column_count: int,
        graph: RelationshipGraph,
        selected_column_scores: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        catalog_column_count = sum(len(table.columns) for table in catalog.tables)
        selected_table_names = set(seed_tables) | set(bridge_tables)
        selected_table_count = len(selected_table_names)
        catalog_table_count = len(catalog.tables)
        return {
            "grounder": "relationship-aware",
            "top_k_tables": self.top_k_tables,
            "top_k_columns": self.top_k_columns,
            "bridge_closure_depth": self.bridge_closure_depth,
            "include_fk_neighbors": self.include_fk_neighbors,
            "include_key_columns": self.include_key_columns,
            "seed_tables": seed_tables,
            "bridge_tables": bridge_tables,
            "relationship_edges": [
                {"source": source, "target": target}
                for source, target in relationship_edges(graph)
                if source in selected_table_names or target in selected_table_names
            ],
            "selected_table_count": selected_table_count,
            "selected_column_count": selected_column_count,
            "catalog_table_count": catalog_table_count,
            "catalog_column_count": catalog_column_count,
            "table_reduction_ratio": _reduction_ratio(selected_table_count, catalog_table_count),
            "column_reduction_ratio": _reduction_ratio(selected_column_count, catalog_column_count),
            "table_scores": {name: round(score, 4) for name, score in table_scores.items()},
            "column_scores": {
                name: round(score, 4) for name, score in (selected_column_scores or {}).items()
            },
        }


def _reduction_ratio(selected_count: int, total_count: int) -> float:
    if total_count <= 0:
        return 0.0
    return round(1.0 - (selected_count / total_count), 4)


def _reference_table_name(reference: str) -> str | None:
    """Resolve the referenced table name, including bare (column-less) references.

    See ``chatsql.grounding.schema_graph._parse_reference_table`` for why a
    dot-less reference is treated as a table-only reference rather than discarded.
    """
    parts = [part.strip('`"[] ') for part in reference.strip().split(".")]
    if len(parts) >= 2:
        return parts[-2] or None
    if parts and parts[0]:
        return parts[0]
    return None

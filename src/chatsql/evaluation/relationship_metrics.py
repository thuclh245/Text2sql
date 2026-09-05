"""Evaluation metrics for relationship and join-path reasoning (Phase 6B)."""

from __future__ import annotations

import re
from typing import Any, cast

from pydantic import BaseModel, ConfigDict
from sqlglot import exp, parse

from chatsql.domain.catalog import DatabaseCatalog
from chatsql.relationships.models import RelationshipPlan

RelationshipEdgeSignature = tuple[str, str, tuple[str, ...], tuple[str, ...]]
RelationshipGoldEdge = tuple[str, str] | RelationshipEdgeSignature


class RelationshipMetrics(BaseModel):
    """Aggregate metrics for relationship and join path reasoning."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    total_cases: int
    edge_recall: float
    edge_precision: float
    wrong_edge_rate: float
    path_coverage: float
    exact_path_accuracy: float
    mean_hop_count: float


def compute_case_relationship_metrics(
    plan: RelationshipPlan,
    gold_edges: set[RelationshipGoldEdge],
    gold_tables: set[str],
) -> dict[str, float | int | bool]:
    """Compute relationship metrics for a single inference case.

    Args:
        plan: Predicted RelationshipPlan
        gold_edges: Set of canonical edge signatures present in gold SQL. Legacy
            two-table pairs are accepted but cannot measure role/key accuracy.
        gold_tables: Set of table names present in gold SQL
    """
    pred_edges = {
        _canonical_relationship_edge(
            e.left_table,
            e.right_table,
            e.left_columns,
            e.right_columns,
        )
        for e in plan.edges
    }
    normalized_gold_edges = {_normalize_gold_edge(edge) for edge in gold_edges}
    gold_pair_edges = {
        (left_table, right_table)
        for left_table, right_table, left_columns, right_columns in normalized_gold_edges
        if not left_columns and not right_columns
    }
    gold_signature_edges = normalized_gold_edges - {
        (left_table, right_table, left_columns, right_columns)
        for left_table, right_table, left_columns, right_columns in normalized_gold_edges
        if not left_columns and not right_columns
    }
    pred_pair_edges = {(left_table, right_table) for left_table, right_table, _, _ in pred_edges}
    pred_tables = {table.lower() for table in plan.tables}
    normalized_gold_tables = {table.lower() for table in gold_tables}

    # Edge metrics
    if not normalized_gold_edges:
        # Single table query
        recall = 1.0 if not pred_edges else 0.0
        precision = 1.0 if not pred_edges else 0.0
        exact_match = len(pred_edges) == 0
    else:
        signature_matches = pred_edges & gold_signature_edges
        matched_pred_pairs = {(left, right) for left, right, _, _ in signature_matches}
        remaining_pred_pairs = pred_pair_edges - matched_pred_pairs
        true_positives = len(signature_matches)
        true_positives += len(remaining_pred_pairs & gold_pair_edges)
        recall = true_positives / len(normalized_gold_edges)
        precision = true_positives / len(pred_edges) if pred_edges else 0.0
        exact_match = True
        if gold_signature_edges:
            exact_match = exact_match and pred_edges == gold_signature_edges
        if gold_pair_edges:
            exact_match = exact_match and pred_pair_edges == gold_pair_edges

    wrong_edge_rate = 1.0 - precision if pred_edges else 0.0
    # Path coverage: all gold tables are contained in predicted tables
    path_cov = 1.0 if normalized_gold_tables.issubset(pred_tables) else 0.0

    return {
        "edge_recall": recall,
        "edge_precision": precision,
        "wrong_edge_rate": wrong_edge_rate,
        "path_coverage": path_cov,
        "exact_match": 1.0 if exact_match else 0.0,
        "hop_count": len(plan.edges),
    }


def extract_gold_relationship_tables(sql: str, catalog: DatabaseCatalog) -> set[str]:
    """Extract table names referenced by SQL, resolving aliases where possible."""
    tables = _sqlglot_tables(sql)
    if tables:
        return tables & set(catalog.table_names())

    found: set[str] = set()
    norm_sql = sql.lower()
    for table in catalog.tables:
        if re.search(rf"\b{re.escape(table.name.lower())}\b", norm_sql):
            found.add(table.name)
    return found


def extract_gold_relationship_edges(
    sql: str,
    catalog: DatabaseCatalog,
) -> set[RelationshipEdgeSignature]:
    """Extract table+column join signatures from column equality predicates."""
    table_names = set(catalog.table_names())
    column_tables: dict[str, set[str]] = {}
    for table in catalog.tables:
        for column in table.columns:
            column_tables.setdefault(column.name.lower(), set()).add(table.name)

    edges: set[RelationshipEdgeSignature] = set()
    for statement in _parse_sql(sql):
        aliases = _table_aliases(statement, table_names)
        for eq in statement.find_all(exp.EQ):
            if not isinstance(eq.left, exp.Column) or not isinstance(eq.right, exp.Column):
                continue
            left_table = _resolve_column_table(eq.left, aliases, column_tables)
            right_table = _resolve_column_table(eq.right, aliases, column_tables)
            if left_table is None or right_table is None or left_table == right_table:
                continue
            edges.add(
                _canonical_relationship_edge(
                    left_table,
                    right_table,
                    (eq.left.name.lower(),),
                    (eq.right.name.lower(),),
                )
            )
    return edges


def aggregate_relationship_metrics(
    case_results: list[dict[str, Any]],
) -> RelationshipMetrics:
    """Aggregate per-case metrics into a summary report."""
    if not case_results:
        return RelationshipMetrics(
            total_cases=0,
            edge_recall=0.0,
            edge_precision=0.0,
            wrong_edge_rate=0.0,
            path_coverage=0.0,
            exact_path_accuracy=0.0,
            mean_hop_count=0.0,
        )

    n = len(case_results)
    mean_recall = sum(r["edge_recall"] for r in case_results) / n
    mean_precision = sum(r["edge_precision"] for r in case_results) / n
    mean_wrong_rate = sum(r["wrong_edge_rate"] for r in case_results) / n
    mean_cov = sum(r["path_coverage"] for r in case_results) / n
    mean_exact = sum(r["exact_match"] for r in case_results) / n
    mean_hops = sum(r["hop_count"] for r in case_results) / n

    return RelationshipMetrics(
        total_cases=n,
        edge_recall=round(mean_recall, 4),
        edge_precision=round(mean_precision, 4),
        wrong_edge_rate=round(mean_wrong_rate, 4),
        path_coverage=round(mean_cov, 4),
        exact_path_accuracy=round(mean_exact, 4),
        mean_hop_count=round(mean_hops, 2),
    )


def _canonical_relationship_edge(
    left_table: str,
    right_table: str,
    left_columns: tuple[str, ...],
    right_columns: tuple[str, ...],
) -> RelationshipEdgeSignature:
    left_table = left_table.lower()
    right_table = right_table.lower()
    normalized_left_columns = tuple(column.lower() for column in left_columns)
    normalized_right_columns = tuple(column.lower() for column in right_columns)
    if left_table <= right_table:
        return (left_table, right_table, normalized_left_columns, normalized_right_columns)
    return (right_table, left_table, normalized_right_columns, normalized_left_columns)


def _normalize_gold_edge(edge: RelationshipGoldEdge) -> RelationshipEdgeSignature:
    if len(edge) == 2:
        left_table, right_table = cast(tuple[str, str], edge)
        return _canonical_relationship_edge(left_table, right_table, (), ())

    left_table, right_table, left_columns, right_columns = cast(RelationshipEdgeSignature, edge)
    return _canonical_relationship_edge(left_table, right_table, left_columns, right_columns)


def _parse_sql(sql: str) -> list[exp.Expression]:
    try:
        return [statement for statement in parse(sql, read="sqlite") if statement is not None]
    except Exception:  # noqa: BLE001 - metrics should not fail the experiment run
        return []


def _sqlglot_tables(sql: str) -> set[str]:
    tables: set[str] = set()
    for statement in _parse_sql(sql):
        for table in statement.find_all(exp.Table):
            tables.add(table.name)
    return tables


def _table_aliases(statement: exp.Expression, table_names: set[str]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for table in statement.find_all(exp.Table):
        table_name = table.name
        if table_name not in table_names:
            continue
        aliases[table_name] = table_name
        alias = table.alias
        if alias:
            aliases[alias] = table_name
    return aliases


def _resolve_column_table(
    column: exp.Column,
    aliases: dict[str, str],
    column_tables: dict[str, set[str]],
) -> str | None:
    qualifier = column.table
    if qualifier:
        return aliases.get(qualifier)

    matches = column_tables.get(column.name.lower(), set())
    if len(matches) == 1:
        return next(iter(matches))
    return None

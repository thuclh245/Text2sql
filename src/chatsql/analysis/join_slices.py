"""Diagnostic join and relationship slices for Phase 6B research."""

from __future__ import annotations

from collections.abc import Callable

from chatsql.domain.catalog import DatabaseCatalog
from chatsql.domain.gold_case import GoldCase
from chatsql.domain.inference_case import InferenceCase
from chatsql.evaluation.relationship_metrics import extract_gold_relationship_tables
from chatsql.relationships.graph import SchemaRelationshipGraph

JoinSlicePredicate = Callable[[InferenceCase, GoldCase, DatabaseCatalog], bool]


def extract_sql_tables(sql: str, catalog: DatabaseCatalog) -> set[str]:
    """Extract referenced table names from a SQL query string.

    Delegates to the sqlglot-AST-based extractor used by relationship metrics so
    join-hop slicing and edge/table-recall metrics agree on the same SQL instead
    of a separate regex scan misreading table names inside string literals or
    comments.
    """
    return extract_gold_relationship_tables(sql, catalog)


def is_single_table_slice(case: InferenceCase, gold: GoldCase, catalog: DatabaseCatalog) -> bool:
    """Slice: Gold query references exactly 0 or 1 table."""
    tables = extract_sql_tables(gold.gold_sql, catalog)
    return len(tables) <= 1


def is_one_hop_join_slice(case: InferenceCase, gold: GoldCase, catalog: DatabaseCatalog) -> bool:
    """Slice: Gold query references exactly 2 tables (1-hop join)."""
    tables = extract_sql_tables(gold.gold_sql, catalog)
    return len(tables) == 2


def is_two_hop_join_slice(case: InferenceCase, gold: GoldCase, catalog: DatabaseCatalog) -> bool:
    """Slice: Gold query references exactly 3 tables (2-hop join)."""
    tables = extract_sql_tables(gold.gold_sql, catalog)
    return len(tables) == 3


def is_three_plus_hop_slice(case: InferenceCase, gold: GoldCase, catalog: DatabaseCatalog) -> bool:
    """Slice: Gold query references 4 or more tables (3+ hop join)."""
    tables = extract_sql_tables(gold.gold_sql, catalog)
    return len(tables) >= 4


def is_multiple_fk_ambiguity_slice(
    case: InferenceCase, gold: GoldCase, catalog: DatabaseCatalog
) -> bool:
    """Slice: The involved tables share 2 or more distinct FK relationships."""
    tables = extract_sql_tables(gold.gold_sql, catalog)
    if len(tables) < 2:
        return False
    graph = SchemaRelationshipGraph(catalog)
    table_list = list(tables)
    for i in range(len(table_list)):
        for j in range(i + 1, len(table_list)):
            edges = graph.edges_between(table_list[i], table_list[j])
            if len(edges) >= 2:
                return True
    return False


def is_bridge_table_required_slice(
    case: InferenceCase, gold: GoldCase, catalog: DatabaseCatalog
) -> bool:
    """Slice: Direct edge does not exist between required tables; needs bridge table."""
    tables = extract_sql_tables(gold.gold_sql, catalog)
    if len(tables) < 3:
        return False
    # If any pair of required tables has no direct edge in the relationship graph
    graph = SchemaRelationshipGraph(catalog)
    table_list = list(tables)
    for i in range(len(table_list)):
        for j in range(i + 1, len(table_list)):
            if not graph.edges_between(table_list[i], table_list[j]):
                return True
    return False


JOIN_SLICES: dict[str, JoinSlicePredicate] = {
    "single_table": is_single_table_slice,
    "1_hop_join": is_one_hop_join_slice,
    "2_hop_join": is_two_hop_join_slice,
    "3_plus_hop_join": is_three_plus_hop_slice,
    "multiple_fk_ambiguity": is_multiple_fk_ambiguity_slice,
    "bridge_table_required": is_bridge_table_required_slice,
}


def classify_join_relationship_slice(
    case: InferenceCase, gold: GoldCase, catalog: DatabaseCatalog
) -> str:
    """Assign one Phase 6B/7A join-relationship slice label to a single case.

    ``bridge_table_required`` and ``multiple_fk_ambiguity`` are cross-cutting
    structural properties independent of hop count, so they take priority over
    the plain hop-count buckets — a bridge-required or FK-ambiguous case is
    reported under that label even if it also happens to be, say, a 2-hop
    join, since that is the harder property Phase 7A/7B slices target.
    """
    if is_bridge_table_required_slice(case, gold, catalog):
        return "bridge_table_required"
    if is_multiple_fk_ambiguity_slice(case, gold, catalog):
        return "multiple_fk_ambiguity"
    if is_three_plus_hop_slice(case, gold, catalog):
        return "3_plus_hop_join"
    if is_two_hop_join_slice(case, gold, catalog):
        return "2_hop_join"
    if is_one_hop_join_slice(case, gold, catalog):
        return "1_hop_join"
    return "single_table"

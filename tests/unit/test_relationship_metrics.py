"""Tests for relationship evaluation metrics."""

from __future__ import annotations

from chatsql.evaluation.relationship_metrics import (
    aggregate_relationship_metrics,
    compute_case_relationship_metrics,
    extract_gold_relationship_edges,
)
from chatsql.domain.catalog import ColumnInfo, DatabaseCatalog, TableInfo
from chatsql.relationships.models import RelationshipEdge, RelationshipPlan


def test_compute_case_relationship_metrics() -> None:
    edge1 = RelationshipEdge(
        left_table="orders",
        right_table="customers",
        left_columns=("customer_id",),
        right_columns=("id",),
    )
    edge2 = RelationshipEdge(
        left_table="orders",
        right_table="order_items",
        left_columns=("id",),
        right_columns=("order_id",),
    )

    plan = RelationshipPlan(
        tables=("customers", "orders", "order_items"),
        edges=(edge1, edge2),
    )

    gold_edges = {
        ("customers", "orders", ("id",), ("customer_id",)),
        ("order_items", "orders", ("order_id",), ("id",)),
    }
    gold_tables = {"customers", "orders", "order_items"}

    res = compute_case_relationship_metrics(plan, gold_edges, gold_tables)

    assert res["edge_recall"] == 1.0
    assert res["edge_precision"] == 1.0
    assert res["wrong_edge_rate"] == 0.0
    assert res["path_coverage"] == 1.0
    assert res["exact_match"] == 1.0
    assert res["hop_count"] == 2


def test_relationship_metrics_distinguish_same_table_pair_different_join_key() -> None:
    plan = RelationshipPlan(
        tables=("airports", "flights"),
        edges=(
            RelationshipEdge(
                left_table="flights",
                right_table="airports",
                left_columns=("arrival_airport",),
                right_columns=("airport_code",),
            ),
        ),
    )

    gold_edges = {("airports", "flights", ("airport_code",), ("departure_airport",))}
    res = compute_case_relationship_metrics(plan, gold_edges, {"airports", "flights"})

    assert res["edge_recall"] == 0.0
    assert res["edge_precision"] == 0.0
    assert res["wrong_edge_rate"] == 1.0
    assert res["exact_match"] == 0.0


def test_mixed_signature_and_legacy_pair_gold_edges_do_not_double_count() -> None:
    """A single predicted edge must not be counted twice just because gold_edges
    mixes a column-specific signature with a legacy bare-table-pair entry for
    the same table pair (both are documented as accepted gold_edges shapes)."""
    plan = RelationshipPlan(
        tables=("orders", "users"),
        edges=(
            RelationshipEdge(
                left_table="orders",
                right_table="users",
                left_columns=("user_id",),
                right_columns=("id",),
            ),
        ),
    )
    gold_edges = {
        ("orders", "users", ("user_id",), ("id",)),
        ("orders", "users"),
    }

    res = compute_case_relationship_metrics(plan, gold_edges, {"orders", "users"})

    assert res["edge_precision"] <= 1.0
    assert res["edge_precision"] == 1.0


def test_extract_gold_relationship_edges_resolves_aliases_and_columns() -> None:
    catalog = DatabaseCatalog(
        database_id="flights_db",
        tables=(
            TableInfo(
                name="airports",
                columns=(ColumnInfo(name="airport_code", data_type="TEXT", is_primary_key=True),),
            ),
            TableInfo(
                name="flights",
                columns=(
                    ColumnInfo(name="departure_airport", data_type="TEXT"),
                    ColumnInfo(name="arrival_airport", data_type="TEXT"),
                ),
            ),
        ),
    )

    edges = extract_gold_relationship_edges(
        "SELECT f.flight_id FROM flights f "
        "JOIN airports a ON f.departure_airport = a.airport_code",
        catalog,
    )

    assert edges == {("airports", "flights", ("airport_code",), ("departure_airport",))}


def test_aggregate_relationship_metrics() -> None:
    case_metrics = [
        {
            "edge_recall": 1.0,
            "edge_precision": 1.0,
            "wrong_edge_rate": 0.0,
            "path_coverage": 1.0,
            "exact_match": 1.0,
            "hop_count": 2,
        },
        {
            "edge_recall": 0.5,
            "edge_precision": 0.5,
            "wrong_edge_rate": 0.5,
            "path_coverage": 1.0,
            "exact_match": 0.0,
            "hop_count": 2,
        },
    ]

    agg = aggregate_relationship_metrics(case_metrics)
    assert agg.total_cases == 2
    assert agg.edge_recall == 0.75
    assert agg.edge_precision == 0.75
    assert agg.wrong_edge_rate == 0.25
    assert agg.path_coverage == 1.0
    assert agg.exact_path_accuracy == 0.5
    assert agg.mean_hop_count == 2.0

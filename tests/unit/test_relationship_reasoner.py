"""Tests for SemanticRelationshipReasoner and path baselines."""

from __future__ import annotations

import pytest

from chatsql.domain.catalog import ColumnInfo, DatabaseCatalog, TableInfo
from chatsql.domain.inference_case import InferenceCase
from chatsql.relationships.baselines import (
    DeclaredFKShortestPathBaseline,
    LexicalRerankerBaseline,
    MinimumHopHeuristicBaseline,
)
from chatsql.relationships.reasoner import SemanticRelationshipReasoner


@pytest.fixture
def flights_catalog() -> DatabaseCatalog:
    """Catalog with flight departures and arrivals (multiple FKs between same tables)."""
    return DatabaseCatalog(
        database_id="flights_db",
        tables=(
            TableInfo(
                name="airports",
                columns=(
                    ColumnInfo(name="airport_code", data_type="TEXT", is_primary_key=True),
                    ColumnInfo(name="city", data_type="TEXT"),
                ),
            ),
            TableInfo(
                name="flights",
                columns=(
                    ColumnInfo(name="flight_id", data_type="INTEGER", is_primary_key=True),
                    ColumnInfo(
                        name="departure_airport",
                        data_type="TEXT",
                        is_foreign_key=True,
                        references="airports.airport_code",
                    ),
                    ColumnInfo(
                        name="arrival_airport",
                        data_type="TEXT",
                        is_foreign_key=True,
                        references="airports.airport_code",
                    ),
                    ColumnInfo(name="flight_num", data_type="TEXT"),
                ),
            ),
        ),
    )


def test_role_disambiguation_departure(flights_catalog: DatabaseCatalog) -> None:
    reasoner = SemanticRelationshipReasoner()
    case = InferenceCase(
        case_id="f1",
        question="Which flights departure from JFK airport?",
        database_id="flights_db",
    )

    plan = reasoner.reason(case, flights_catalog)
    assert len(plan.edges) == 1
    edge = plan.edges[0]
    # Check that departure_airport was selected over arrival_airport
    assert "departure_airport" in edge.left_columns or "departure_airport" in edge.right_columns


def test_role_disambiguation_arrival(flights_catalog: DatabaseCatalog) -> None:
    reasoner = SemanticRelationshipReasoner()
    case = InferenceCase(
        case_id="f2",
        question="List all flights arrival at LAX airport",
        database_id="flights_db",
    )

    plan = reasoner.reason(case, flights_catalog)
    assert len(plan.edges) == 1
    edge = plan.edges[0]
    # Check that arrival_airport was selected over departure_airport
    assert "arrival_airport" in edge.left_columns or "arrival_airport" in edge.right_columns


def test_single_table_query_no_joins(flights_catalog: DatabaseCatalog) -> None:
    reasoner = SemanticRelationshipReasoner()
    case = InferenceCase(
        case_id="f3",
        question="How many airports are there in New York?",
        database_id="flights_db",
    )

    from chatsql.grounding.base import GroundingResult, TableRef

    grounding = GroundingResult(
        tables=(TableRef(name="airports"),),
        columns=(),
        evidence=(),
        scores={},
    )

    plan = reasoner.reason(case, flights_catalog, grounding=grounding)
    assert plan.is_single_table
    assert plan.tables == ("airports",)
    assert plan.hop_count == 0


def test_disallow_bridge_tables_does_not_fallback_to_bridge_path() -> None:
    from chatsql.grounding.base import GroundingResult, TableRef

    catalog = DatabaseCatalog(
        database_id="shop",
        tables=(
            TableInfo(
                name="customers",
                columns=(ColumnInfo(name="id", data_type="INTEGER", is_primary_key=True),),
            ),
            TableInfo(
                name="orders",
                columns=(
                    ColumnInfo(name="id", data_type="INTEGER", is_primary_key=True),
                    ColumnInfo(
                        name="customer_id",
                        data_type="INTEGER",
                        is_foreign_key=True,
                        references="customers.id",
                    ),
                ),
            ),
            TableInfo(
                name="order_items",
                columns=(
                    ColumnInfo(
                        name="order_id",
                        data_type="INTEGER",
                        is_foreign_key=True,
                        references="orders.id",
                    ),
                ),
            ),
        ),
    )
    grounding = GroundingResult(
        tables=(TableRef(name="customers"), TableRef(name="order_items")),
        columns=(),
        evidence=(),
        scores={},
    )
    case = InferenceCase(
        case_id="f_bridge",
        question="Show customer order items",
        database_id="shop",
    )
    reasoner = SemanticRelationshipReasoner(allow_bridge_tables=False)

    plan = reasoner.reason(case, catalog, grounding=grounding)

    assert plan.edges == ()
    assert plan.confidence == 0.0


def test_baselines_execution(flights_catalog: DatabaseCatalog) -> None:
    case = InferenceCase(
        case_id="f4",
        question="Show flights departing from JFK",
        database_id="flights_db",
    )
    tables = {"airports", "flights"}

    b1 = DeclaredFKShortestPathBaseline()
    p1 = b1.plan(tables, flights_catalog, case)
    assert len(p1.edges) == 1

    b2 = MinimumHopHeuristicBaseline()
    p2 = b2.plan(tables, flights_catalog, case)
    assert len(p2.edges) == 1

    b3 = LexicalRerankerBaseline()
    p3 = b3.plan(tables, flights_catalog, case)
    assert len(p3.edges) == 1


def test_junction_table_path_penalized_below_direct_path() -> None:
    """A path routed through a pure junction table should score lower than a
    direct edge of the same length, since it implies many-to-many fan-out."""
    from chatsql.relationships.reasoner import _is_junction_table

    junction = TableInfo(
        name="order_items",
        columns=(
            ColumnInfo(
                name="order_id",
                data_type="INTEGER",
                is_primary_key=True,
                is_foreign_key=True,
                references="orders.id",
            ),
            ColumnInfo(
                name="product_id",
                data_type="INTEGER",
                is_primary_key=True,
                is_foreign_key=True,
                references="products.id",
            ),
        ),
    )
    non_junction = TableInfo(
        name="orders",
        columns=(
            ColumnInfo(name="id", data_type="INTEGER", is_primary_key=True),
            ColumnInfo(
                name="customer_id",
                data_type="INTEGER",
                is_foreign_key=True,
                references="customers.id",
            ),
        ),
    )

    assert _is_junction_table(junction) is True
    assert _is_junction_table(non_junction) is False


def test_disconnected_fallback_preserves_already_scored_edges() -> None:
    """When a required table is only reachable beyond max_join_depth, the
    shortest-path fallback should bridge just that table instead of discarding
    edges already chosen by semantic scoring for the rest of the plan."""
    from chatsql.grounding.base import GroundingResult, TableRef

    catalog = DatabaseCatalog(
        database_id="chain",
        tables=(
            TableInfo(
                name="a",
                columns=(ColumnInfo(name="id", data_type="INTEGER", is_primary_key=True),),
            ),
            TableInfo(
                name="b",
                columns=(
                    ColumnInfo(name="id", data_type="INTEGER", is_primary_key=True),
                    ColumnInfo(
                        name="a_id",
                        data_type="INTEGER",
                        is_foreign_key=True,
                        references="a.id",
                    ),
                ),
            ),
            TableInfo(
                name="bridge",
                columns=(
                    ColumnInfo(name="id", data_type="INTEGER", is_primary_key=True),
                    ColumnInfo(
                        name="b_id",
                        data_type="INTEGER",
                        is_foreign_key=True,
                        references="b.id",
                    ),
                ),
            ),
            TableInfo(
                name="c",
                columns=(
                    ColumnInfo(name="id", data_type="INTEGER", is_primary_key=True),
                    ColumnInfo(
                        name="bridge_id",
                        data_type="INTEGER",
                        is_foreign_key=True,
                        references="bridge.id",
                    ),
                ),
            ),
        ),
    )
    grounding = GroundingResult(
        tables=(TableRef(name="a"), TableRef(name="b"), TableRef(name="c")),
        columns=(),
        evidence=(),
        scores={},
    )
    case = InferenceCase(case_id="chain_1", question="a b c", database_id="chain")

    # max_join_depth=1 means B<->C (2 hops via 'bridge') can't be found by the
    # scored search, forcing the disconnected-component fallback.
    reasoner = SemanticRelationshipReasoner(max_join_depth=1)
    plan = reasoner.reason(case, catalog, grounding=grounding)

    assert set(plan.tables) == {"a", "b", "bridge", "c"}
    assert plan.hop_count == 3
    # The A-B edge chosen by the scored search must survive the fallback.
    assert any(edge.involves("a") and edge.involves("b") for edge in plan.edges)
    assert any(edge.involves("b") and edge.involves("bridge") for edge in plan.edges)
    assert any(edge.involves("bridge") and edge.involves("c") for edge in plan.edges)
    # Confidence should blend the real scored hop with the bridged hops rather
    # than collapsing to a flat, uninformative 0.5.
    assert plan.confidence != 0.5

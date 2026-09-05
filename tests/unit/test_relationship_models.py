"""Tests for Phase 6B relationship domain models."""

from __future__ import annotations

import pytest

from chatsql.relationships.models import (
    Cardinality,
    RelationshipEdge,
    RelationshipPlan,
    RelationType,
)


def test_relationship_edge_properties() -> None:
    edge = RelationshipEdge(
        left_table="orders",
        right_table="customers",
        left_columns=("customer_id",),
        right_columns=("id",),
        relation_type=RelationType.FOREIGN_KEY.value,
        cardinality=Cardinality.MANY_TO_ONE.value,
        provenance="declared_fk",
    )

    assert edge.involves("orders")
    assert edge.involves("customers")
    assert not edge.involves("products")

    assert edge.other_table("orders") == "customers"
    assert edge.other_table("customers") == "orders"

    with pytest.raises(ValueError, match="not an endpoint"):
        edge.other_table("products")

    assert edge.canonical_pair() == ("customers", "orders")


def test_relationship_plan_properties() -> None:
    single_table_plan = RelationshipPlan(
        tables=("customers",),
        edges=(),
        grain=("customers.id",),
    )
    assert single_table_plan.is_single_table
    assert single_table_plan.hop_count == 0
    assert "no joins" in single_table_plan.summary()

    edge = RelationshipEdge(
        left_table="orders",
        right_table="customers",
        left_columns=("customer_id",),
        right_columns=("id",),
    )
    multi_table_plan = RelationshipPlan(
        tables=("customers", "orders"),
        edges=(edge,),
        grain=("orders.id",),
    )
    assert not multi_table_plan.is_single_table
    assert multi_table_plan.hop_count == 1
    assert "orders.customer_id = customers.id" in multi_table_plan.summary()

"""Tests for Phase 6B diagnostic join slices."""

from __future__ import annotations

import pytest

from chatsql.analysis.join_slices import (
    is_bridge_table_required_slice,
    is_one_hop_join_slice,
    is_single_table_slice,
    is_two_hop_join_slice,
)
from chatsql.domain.catalog import ColumnInfo, DatabaseCatalog, TableInfo
from chatsql.domain.gold_case import GoldCase
from chatsql.domain.inference_case import InferenceCase


@pytest.fixture
def slice_test_catalog() -> DatabaseCatalog:
    return DatabaseCatalog(
        database_id="test_db",
        tables=(
            TableInfo(
                name="customers",
                columns=(
                    ColumnInfo(name="id", data_type="INTEGER", is_primary_key=True),
                    ColumnInfo(name="name", data_type="TEXT"),
                ),
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
                    ColumnInfo(
                        name="product_id",
                        data_type="INTEGER",
                        is_foreign_key=True,
                        references="products.id",
                    ),
                ),
            ),
            TableInfo(
                name="products",
                columns=(
                    ColumnInfo(name="id", data_type="INTEGER", is_primary_key=True),
                    ColumnInfo(name="title", data_type="TEXT"),
                ),
            ),
        ),
    )


def test_join_slices_detection(slice_test_catalog: DatabaseCatalog) -> None:
    case = InferenceCase(case_id="c1", question="test", database_id="test_db")

    # Single table query
    g1 = GoldCase(case_id="c1", gold_sql="SELECT name FROM customers")
    assert is_single_table_slice(case, g1, slice_test_catalog)
    assert not is_one_hop_join_slice(case, g1, slice_test_catalog)

    # 1-hop join
    g2 = GoldCase(
        case_id="c1",
        gold_sql="SELECT c.name, o.id FROM customers c JOIN orders o ON c.id = o.customer_id",
    )
    assert not is_single_table_slice(case, g2, slice_test_catalog)
    assert is_one_hop_join_slice(case, g2, slice_test_catalog)
    assert not is_two_hop_join_slice(case, g2, slice_test_catalog)

    # 2-hop join
    g3 = GoldCase(
        case_id="c1",
        gold_sql=(
            "SELECT c.name, oi.product_id FROM customers c "
            "JOIN orders o ON c.id = o.customer_id "
            "JOIN order_items oi ON o.id = oi.order_id"
        ),
    )
    assert is_two_hop_join_slice(case, g3, slice_test_catalog)

    # Bridge table required (customers -> order_items requires orders)
    g_bridge = GoldCase(
        case_id="c1",
        gold_sql=(
            "SELECT customers.name, products.title, order_items.order_id "
            "FROM customers, products, order_items"
        ),
    )
    assert is_bridge_table_required_slice(case, g_bridge, slice_test_catalog)

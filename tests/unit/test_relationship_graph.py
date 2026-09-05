"""Tests for SchemaRelationshipGraph and path finding."""

from __future__ import annotations

import pytest

from chatsql.domain.catalog import ColumnInfo, DatabaseCatalog, TableInfo
from chatsql.relationships.graph import SchemaRelationshipGraph


@pytest.fixture
def sample_ecommerce_catalog() -> DatabaseCatalog:
    """Catalog with: customers, orders, order_items, products, and categories."""
    return DatabaseCatalog(
        database_id="ecommerce",
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
                    ColumnInfo(name="order_date", data_type="TEXT"),
                ),
            ),
            TableInfo(
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
                    ColumnInfo(name="quantity", data_type="INTEGER"),
                ),
            ),
            TableInfo(
                name="products",
                columns=(
                    ColumnInfo(name="id", data_type="INTEGER", is_primary_key=True),
                    ColumnInfo(name="title", data_type="TEXT"),
                    ColumnInfo(
                        name="category_id",
                        data_type="INTEGER",
                        is_foreign_key=True,
                        references="categories.id",
                    ),
                ),
            ),
            TableInfo(
                name="categories",
                columns=(
                    ColumnInfo(name="id", data_type="INTEGER", is_primary_key=True),
                    ColumnInfo(name="name", data_type="TEXT"),
                ),
            ),
        ),
    )


def test_graph_construction(sample_ecommerce_catalog: DatabaseCatalog) -> None:
    graph = SchemaRelationshipGraph(sample_ecommerce_catalog)

    assert len(graph.all_edges) == 4
    assert graph.neighbors("customers") == {"orders"}
    assert graph.neighbors("order_items") == {"orders", "products"}
    assert graph.neighbors("categories") == {"products"}

    order_item_edges = [
        edge for edge in graph.all_edges if edge.left_table == "order_items"
    ]
    assert {edge.cardinality for edge in order_item_edges} == {"MANY_TO_ONE"}


def test_shortest_path_direct(sample_ecommerce_catalog: DatabaseCatalog) -> None:
    graph = SchemaRelationshipGraph(sample_ecommerce_catalog)

    path = graph.shortest_path("customers", "orders")
    assert path is not None
    assert len(path) == 1
    assert path[0].involves("customers")
    assert path[0].involves("orders")


def test_shortest_path_multi_hop_bridge(sample_ecommerce_catalog: DatabaseCatalog) -> None:
    graph = SchemaRelationshipGraph(sample_ecommerce_catalog)

    # customers -> orders -> order_items -> products -> categories (4 hops)
    path = graph.shortest_path("customers", "categories")
    assert path is not None
    assert len(path) == 4

    # Connect customers and products via order_items bridge
    conn_tables, edges = graph.connect_tables_shortest({"customers", "products"})
    assert conn_tables == {"customers", "orders", "order_items", "products"}
    assert len(edges) == 3


def test_find_all_paths(sample_ecommerce_catalog: DatabaseCatalog) -> None:
    graph = SchemaRelationshipGraph(sample_ecommerce_catalog)

    paths = graph.find_paths_between("customers", "products", max_depth=4)
    assert len(paths) >= 1
    assert len(paths[0]) == 3  # customers -> orders -> order_items -> products

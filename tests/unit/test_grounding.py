"""Unit tests for grounding components, registry, and retrieval evaluator."""

from __future__ import annotations

import pytest

import chatsql.grounding.full_schema  # noqa: F401 - imported for @register side effects
import chatsql.grounding.lite_sql_adapter  # noqa: F401 - imported for @register side effects
import chatsql.grounding.relationship_aware  # noqa: F401 - imported for @register side effects
import chatsql.grounding.simple_dense  # noqa: F401 - imported for @register side effects
from chatsql.domain.catalog import ColumnInfo, DatabaseCatalog, TableInfo
from chatsql.domain.gold_case import GoldCase
from chatsql.domain.inference_case import InferenceCase
from chatsql.evaluation.retrieval import RetrievalEvaluator
from chatsql.grounding.base import ColumnRef, GroundingResult, TableRef
from chatsql.grounding.full_schema import FullSchemaGrounder
from chatsql.grounding.lite_sql_adapter import LitESQLGrounderAdapter
from chatsql.grounding.registry import get_grounder, list_grounders
from chatsql.grounding.relationship_aware import RelationshipAwareGrounder
from chatsql.grounding.schema_graph import build_relationship_graph, expand_fk_neighbors
from chatsql.grounding.simple_dense import SimpleDenseGrounder


@pytest.fixture()
def sample_catalog() -> DatabaseCatalog:
    col1 = ColumnInfo(name="id", data_type="INTEGER", is_primary_key=True)
    col2 = ColumnInfo(name="name", data_type="TEXT")
    col3 = ColumnInfo(
        name="user_id",
        data_type="INTEGER",
        is_foreign_key=True,
        references="users.id",
    )
    tbl_users = TableInfo(name="users", columns=(col1, col2))
    tbl_orders = TableInfo(name="orders", columns=(col1, col3))
    return DatabaseCatalog(database_id="shop", tables=(tbl_users, tbl_orders))


@pytest.fixture()
def relationship_catalog() -> DatabaseCatalog:
    users = TableInfo(
        name="users",
        columns=(
            ColumnInfo(name="id", data_type="INTEGER", is_primary_key=True),
            ColumnInfo(name="name", data_type="TEXT", description="customer display name"),
        ),
    )
    orders = TableInfo(
        name="orders",
        columns=(
            ColumnInfo(name="id", data_type="INTEGER", is_primary_key=True),
            ColumnInfo(
                name="user_id",
                data_type="INTEGER",
                is_foreign_key=True,
                references="users.id",
            ),
        ),
    )
    products = TableInfo(
        name="products",
        columns=(
            ColumnInfo(name="id", data_type="INTEGER", is_primary_key=True),
            ColumnInfo(name="sku", data_type="TEXT"),
        ),
    )
    broken = TableInfo(
        name="broken_refs",
        columns=(
            ColumnInfo(
                name="bad_fk",
                data_type="INTEGER",
                is_foreign_key=True,
                references="not_a_reference",
            ),
            ColumnInfo(
                name="missing_fk",
                data_type="INTEGER",
                is_foreign_key=True,
                references="missing_table.id",
            ),
        ),
    )
    return DatabaseCatalog(database_id="shop", tables=(users, orders, products, broken))


@pytest.fixture()
def sample_case() -> InferenceCase:
    return InferenceCase(
        case_id="c1",
        question="Show all orders for users",
        database_id="shop",
    )


class TestGroundingRegistry:
    def test_registered_grounders(self) -> None:
        grounders = list_grounders()
        assert "full-schema" in grounders
        assert "simple-dense" in grounders
        assert "lite-sql" in grounders
        assert "relationship-aware" in grounders

    def test_get_grounder_full_schema(self) -> None:
        cls = get_grounder("full-schema")
        assert cls is FullSchemaGrounder

    def test_get_grounder_relationship_aware(self) -> None:
        cls = get_grounder("relationship-aware")
        assert cls is RelationshipAwareGrounder


class TestFullSchemaGrounder:
    def test_full_schema_returns_all_tables_and_columns(
        self, sample_case: InferenceCase, sample_catalog: DatabaseCatalog
    ) -> None:
        grounder = FullSchemaGrounder()
        res = grounder.ground(sample_case, sample_catalog)

        assert len(res.tables) == 2
        assert len(res.columns) == 4
        assert res.table_names == {"users", "orders"}


class TestSimpleDenseGrounder:
    def test_simple_dense_ranks_tables(
        self, sample_case: InferenceCase, sample_catalog: DatabaseCatalog
    ) -> None:
        grounder = SimpleDenseGrounder(top_k_tables=1)
        res = grounder.ground(sample_case, sample_catalog)

        assert len(res.tables) == 1
        assert "orders" in res.table_names or "users" in res.table_names

    def test_simple_dense_respects_top_k_columns(
        self, sample_case: InferenceCase, sample_catalog: DatabaseCatalog
    ) -> None:
        grounder = SimpleDenseGrounder(top_k_tables=2, top_k_columns=1)
        res = grounder.ground(sample_case, sample_catalog)

        assert len(res.columns) == 1


class TestLitESQLGrounderAdapter:
    def test_lite_sql_grounder_adapter(
        self, sample_case: InferenceCase, sample_catalog: DatabaseCatalog
    ) -> None:
        grounder = LitESQLGrounderAdapter(
            top_k_tables=1,
            retriever=lambda lite_input: [lite_input["schema"][1]["table_name"]],
        )
        res = grounder.ground(sample_case, sample_catalog)

        assert len(res.tables) == 1
        assert res.tables[0].name == "orders"

    def test_lite_sql_grounder_requires_real_retriever(
        self, sample_case: InferenceCase, sample_catalog: DatabaseCatalog
    ) -> None:
        grounder = LitESQLGrounderAdapter(top_k_tables=2)

        with pytest.raises(NotImplementedError, match="requires an upstream retriever"):
            grounder.ground(sample_case, sample_catalog)


class TestSchemaGraph:
    def test_build_relationship_graph_from_foreign_keys(
        self, relationship_catalog: DatabaseCatalog
    ) -> None:
        graph = build_relationship_graph(relationship_catalog)

        assert graph["users"] == {"orders"}
        assert graph["orders"] == {"users"}
        assert graph["products"] == set()

    def test_expand_fk_neighbors_respects_depth(self) -> None:
        graph = {
            "users": {"orders"},
            "orders": {"users", "order_items"},
            "order_items": {"orders", "products"},
            "products": {"order_items"},
        }

        assert expand_fk_neighbors({"users"}, graph, depth=1) == {"users", "orders"}
        assert expand_fk_neighbors({"users"}, graph, depth=2) == {
            "users",
            "orders",
            "order_items",
        }

    def test_expand_fk_neighbors_avoids_duplicates_and_can_disable(self) -> None:
        graph = {"users": {"orders"}, "orders": {"users"}}

        expanded = expand_fk_neighbors({"users", "orders"}, graph, depth=2)
        disabled = expand_fk_neighbors(
            {"users"},
            graph,
            depth=2,
            include_fk_neighbors=False,
        )

        assert expanded == {"users", "orders"}
        assert disabled == {"users"}

    def test_malformed_and_missing_references_are_ignored(
        self, relationship_catalog: DatabaseCatalog
    ) -> None:
        graph = build_relationship_graph(relationship_catalog)

        assert graph["broken_refs"] == set()

    def test_schema_qualified_references_use_table_segment(self) -> None:
        parent = TableInfo(
            name="users",
            columns=(ColumnInfo(name="id", data_type="INTEGER", is_primary_key=True),),
        )
        child = TableInfo(
            name="orders",
            columns=(
                ColumnInfo(
                    name="user_id",
                    data_type="INTEGER",
                    is_foreign_key=True,
                    references='"main"."users"."id"',
                ),
            ),
        )
        catalog = DatabaseCatalog(database_id="shop", tables=(parent, child))

        graph = build_relationship_graph(catalog)

        assert graph["users"] == {"orders"}
        assert graph["orders"] == {"users"}

    def test_bare_table_reference_without_column_resolves(self) -> None:
        """A dot-less ``REFERENCES parent_table`` (no explicit column) is valid
        SQL shorthand for the parent's primary key and should resolve to an
        edge, matching SchemaRelationshipGraph's handling of the same input."""
        parent = TableInfo(
            name="customers",
            columns=(ColumnInfo(name="id", data_type="INTEGER", is_primary_key=True),),
        )
        child = TableInfo(
            name="orders",
            columns=(
                ColumnInfo(
                    name="customer_id",
                    data_type="INTEGER",
                    is_foreign_key=True,
                    references="customers",
                ),
            ),
        )
        catalog = DatabaseCatalog(database_id="shop", tables=(parent, child))

        graph = build_relationship_graph(catalog)

        assert graph["customers"] == {"orders"}
        assert graph["orders"] == {"customers"}


class TestRelationshipAwareGrounder:
    def test_retrieves_question_matching_tables(
        self, relationship_catalog: DatabaseCatalog
    ) -> None:
        grounder = RelationshipAwareGrounder(
            top_k_tables=1,
            top_k_columns=10,
            include_fk_neighbors=False,
        )
        case = InferenceCase(
            case_id="c2",
            question="Show customer names",
            database_id="shop",
        )

        res = grounder.ground(case, relationship_catalog)

        assert res.table_names == {"users"}
        assert res.metadata["seed_tables"] == ["users"]

    def test_adds_foreign_key_bridge_table(self, relationship_catalog: DatabaseCatalog) -> None:
        grounder = RelationshipAwareGrounder(
            top_k_tables=1,
            top_k_columns=10,
            bridge_closure_depth=1,
            include_fk_neighbors=True,
        )
        case = InferenceCase(
            case_id="c3",
            question="Show customer names",
            database_id="shop",
        )

        res = grounder.ground(case, relationship_catalog)

        assert res.table_names == {"users", "orders"}
        assert res.metadata["seed_tables"] == ["users"]
        assert res.metadata["bridge_tables"] == ["orders"]

    def test_respects_table_and_column_caps(self, relationship_catalog: DatabaseCatalog) -> None:
        grounder = RelationshipAwareGrounder(
            top_k_tables=1,
            top_k_columns=2,
            include_fk_neighbors=False,
        )
        case = InferenceCase(case_id="c4", question="Show orders", database_id="shop")

        res = grounder.ground(case, relationship_catalog)

        assert len(res.tables) == 1
        assert len(res.columns) == 2
        assert {column.column_name for column in res.columns} == {"id", "user_id"}

    def test_records_expected_metadata(self, relationship_catalog: DatabaseCatalog) -> None:
        grounder = RelationshipAwareGrounder(top_k_tables=1, top_k_columns=2)
        case = InferenceCase(
            case_id="c5",
            question="Show orders",
            database_id="shop",
            evidence={"text": "Use customer relationships"},
        )

        res = grounder.ground(case, relationship_catalog)

        assert res.metadata["grounder"] == "relationship-aware"
        assert res.metadata["bridge_closure_depth"] == 1
        assert res.metadata["include_fk_neighbors"] is True
        assert res.metadata["selected_table_count"] == len(res.tables)
        assert res.metadata["selected_column_count"] == len(res.columns)
        assert "table_scores" in res.metadata
        assert "column_scores" in res.metadata
        assert "relationship_edges" in res.metadata

    def test_preserves_join_keys_for_selected_relationship_tables(
        self, relationship_catalog: DatabaseCatalog
    ) -> None:
        grounder = RelationshipAwareGrounder(
            top_k_tables=1,
            top_k_columns=1,
            bridge_closure_depth=1,
            include_fk_neighbors=True,
        )
        case = InferenceCase(
            case_id="c6",
            question="Show customer names",
            database_id="shop",
        )

        res = grounder.ground(case, relationship_catalog)

        assert ("orders", "user_id") in res.column_names
        assert ("users", "id") in res.column_names
        assert any(
            edge == {"source": "orders", "target": "users"}
            for edge in res.metadata["relationship_edges"]
        )

    def test_can_disable_key_column_preservation(
        self, relationship_catalog: DatabaseCatalog
    ) -> None:
        grounder = RelationshipAwareGrounder(
            top_k_tables=1,
            top_k_columns=1,
            bridge_closure_depth=1,
            include_fk_neighbors=True,
            include_key_columns=False,
        )
        case = InferenceCase(
            case_id="c7",
            question="Show customer names",
            database_id="shop",
        )

        res = grounder.ground(case, relationship_catalog)

        assert len(res.columns) == 1


class TestRetrievalEvaluator:
    def test_retrieval_evaluator_perfect_match(
        self, sample_case: InferenceCase, sample_catalog: DatabaseCatalog
    ) -> None:
        grounder = FullSchemaGrounder()
        res = grounder.ground(sample_case, sample_catalog)

        gold = GoldCase(
            case_id="c1",
            gold_sql="SELECT * FROM users JOIN orders ON users.id = orders.user_id",
            gold_tables=("users", "orders"),
        )

        evaluator = RetrievalEvaluator()
        metrics = evaluator.evaluate_case(res, gold)

        assert metrics.table_recall == 1.0
        assert metrics.complete_schema_recall == 1.0
        assert metrics.precision == 1.0

    def test_retrieval_evaluator_parses_tables_from_gold_sql(
        self, sample_case: InferenceCase, sample_catalog: DatabaseCatalog
    ) -> None:
        res = FullSchemaGrounder().ground(sample_case, sample_catalog)
        gold = GoldCase(
            case_id="c1",
            gold_sql="SELECT users.name FROM users JOIN orders ON users.id = orders.user_id",
        )

        metrics = RetrievalEvaluator().evaluate_case(res, gold)

        assert metrics.table_recall == 1.0

    def test_retrieval_evaluator_matches_string_gold_columns(
        self, sample_case: InferenceCase, sample_catalog: DatabaseCatalog
    ) -> None:
        res = FullSchemaGrounder().ground(sample_case, sample_catalog)
        gold = GoldCase(
            case_id="c1",
            gold_sql="SELECT users.name FROM users",
            gold_tables=("users",),
            gold_columns=("name",),
        )

        metrics = RetrievalEvaluator().evaluate_case(res, gold)

        assert metrics.column_recall == 1.0

    def test_retrieval_evaluator_requires_matching_table_for_qualified_gold_columns(
        self,
    ) -> None:
        grounding = GroundingResult(
            tables=(TableRef(name="orders"),),
            columns=(ColumnRef(table_name="orders", column_name="id"),),
        )
        gold = GoldCase(
            case_id="c2",
            gold_sql="SELECT users.id FROM users",
            gold_tables=("users",),
            gold_columns=("users.id",),
        )

        metrics = RetrievalEvaluator().evaluate_case(grounding, gold)

        assert metrics.column_recall == 0.0
        assert metrics.complete_schema_recall == 0.0

    def test_retrieval_evaluator_parses_aliased_gold_columns_as_table_qualified(
        self,
    ) -> None:
        grounding = GroundingResult(
            tables=(TableRef(name="users"), TableRef(name="orders")),
            columns=(
                ColumnRef(table_name="users", column_name="name"),
                ColumnRef(table_name="orders", column_name="user_id"),
            ),
        )
        gold = GoldCase(
            case_id="c3",
            gold_sql=(
                "SELECT u.name FROM users AS u "
                "JOIN orders AS o ON u.id = o.user_id"
            ),
        )

        metrics = RetrievalEvaluator().evaluate_case(grounding, gold)

        assert metrics.table_recall == 1.0
        assert metrics.column_recall == pytest.approx(2 / 3)
        assert metrics.complete_schema_recall == 0.0

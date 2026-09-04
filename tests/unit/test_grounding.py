"""Unit tests for Phase 4 grounding components, registry, and retrieval evaluator."""

from __future__ import annotations

import pytest

import chatsql.grounding.full_schema  # noqa: F401 - imported for @register side effects
import chatsql.grounding.lite_sql_adapter  # noqa: F401 - imported for @register side effects
import chatsql.grounding.simple_dense  # noqa: F401 - imported for @register side effects
from chatsql.domain.catalog import ColumnInfo, DatabaseCatalog, TableInfo
from chatsql.domain.gold_case import GoldCase
from chatsql.domain.inference_case import InferenceCase
from chatsql.evaluation.retrieval import RetrievalEvaluator
from chatsql.grounding.full_schema import FullSchemaGrounder
from chatsql.grounding.lite_sql_adapter import LitESQLGrounderAdapter
from chatsql.grounding.registry import get_grounder, list_grounders
from chatsql.grounding.simple_dense import SimpleDenseGrounder


@pytest.fixture()
def sample_catalog() -> DatabaseCatalog:
    col1 = ColumnInfo(name="id", data_type="INTEGER", is_primary_key=True)
    col2 = ColumnInfo(name="name", data_type="TEXT")
    col3 = ColumnInfo(name="user_id", data_type="INTEGER", is_foreign_key=True)
    tbl_users = TableInfo(name="users", columns=(col1, col2))
    tbl_orders = TableInfo(name="orders", columns=(col1, col3))
    return DatabaseCatalog(database_id="shop", tables=(tbl_users, tbl_orders))


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

    def test_get_grounder_full_schema(self) -> None:
        cls = get_grounder("full-schema")
        assert cls is FullSchemaGrounder


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

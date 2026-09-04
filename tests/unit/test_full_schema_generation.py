"""Tests for full-schema SQL generation components."""

from __future__ import annotations

import pytest

from chatsql.domain.catalog import ColumnInfo, DatabaseCatalog, TableInfo
from chatsql.domain.inference_case import InferenceCase
from chatsql.generation.llm_client import StubLLMClient
from chatsql.generation.parser import extract_sql
from chatsql.generation.prompt_builder import PROMPT_VERSION, FullSchemaPromptBuilder
from chatsql.strategies.full_schema import FullSchemaStrategy

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def simple_catalog() -> DatabaseCatalog:
    col_id = ColumnInfo(name="id", data_type="INTEGER", is_primary_key=True)
    col_name = ColumnInfo(name="name", data_type="TEXT")
    col_price = ColumnInfo(name="price", data_type="REAL")
    table = TableInfo(name="products", columns=(col_id, col_name, col_price))
    return DatabaseCatalog(database_id="shop", tables=(table,))


@pytest.fixture()
def simple_case() -> InferenceCase:
    return InferenceCase(
        case_id="bird_1",
        question="How many products are there?",
        database_id="shop",
        evidence={"text": "count all rows"},
    )


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------


class TestSQLParser:
    def test_extracts_fenced_sql(self) -> None:
        raw = "Let me think...\n```sql\nSELECT COUNT(*) FROM products\n```"
        sql = extract_sql(raw)
        assert sql == "SELECT COUNT(*) FROM products"

    def test_extracts_last_fence_in_cot(self) -> None:
        raw = "```sql\nSELECT 1\n```\nActually:\n```sql\nSELECT COUNT(*) FROM t\n```"
        sql = extract_sql(raw)
        assert sql == "SELECT COUNT(*) FROM t"

    def test_extracts_plain_select(self) -> None:
        raw = "The answer is SELECT * FROM users"
        sql = extract_sql(raw)
        assert sql is not None
        assert sql.upper().startswith("SELECT")

    def test_returns_none_for_empty(self) -> None:
        assert extract_sql("No SQL here.") is None

    def test_strips_trailing_semicolon(self) -> None:
        raw = "```sql\nSELECT 1;\n```"
        sql = extract_sql(raw)
        assert sql == "SELECT 1"


# ---------------------------------------------------------------------------
# Prompt builder tests
# ---------------------------------------------------------------------------


class TestPromptBuilder:
    def test_prompt_contains_schema(
        self,
        simple_case: InferenceCase,
        simple_catalog: DatabaseCatalog,
    ) -> None:
        builder = FullSchemaPromptBuilder()
        prompt, _ = builder.build(simple_case, simple_catalog)
        assert "products" in prompt
        assert "price" in prompt

    def test_prompt_contains_question(
        self,
        simple_case: InferenceCase,
        simple_catalog: DatabaseCatalog,
    ) -> None:
        builder = FullSchemaPromptBuilder()
        prompt, _ = builder.build(simple_case, simple_catalog)
        assert "How many products" in prompt

    def test_prompt_contains_evidence(
        self,
        simple_case: InferenceCase,
        simple_catalog: DatabaseCatalog,
    ) -> None:
        builder = FullSchemaPromptBuilder()
        prompt, _ = builder.build(simple_case, simple_catalog)
        assert "count all rows" in prompt

    def test_context_view_populated(
        self,
        simple_case: InferenceCase,
        simple_catalog: DatabaseCatalog,
    ) -> None:
        builder = FullSchemaPromptBuilder()
        _, context = builder.build(simple_case, simple_catalog)
        assert "products" in context.schema_text
        assert context.question == simple_case.question
        assert context.token_estimate is not None

    def test_prompt_version_constant(self) -> None:
        assert PROMPT_VERSION != ""
        assert "full-schema" in PROMPT_VERSION


# ---------------------------------------------------------------------------
# FullSchemaStrategy tests
# ---------------------------------------------------------------------------


class TestFullSchemaStrategy:
    def test_strategy_returns_prediction(
        self, simple_case: InferenceCase, simple_catalog: DatabaseCatalog
    ) -> None:
        stub = StubLLMClient("SELECT COUNT(*) FROM products")
        strategy = FullSchemaStrategy(stub)
        pred = strategy.run(simple_case, simple_catalog)

        assert pred.case_id == "bird_1"
        assert "SELECT" in pred.predicted_sql.upper()

    def test_strategy_does_not_receive_gold(
        self, simple_case: InferenceCase, simple_catalog: DatabaseCatalog
    ) -> None:
        """Strategy.run() only receives InferenceCase + catalog — never GoldCase."""
        import inspect

        from chatsql.domain.gold_case import GoldCase

        stub = StubLLMClient()
        strategy = FullSchemaStrategy(stub)
        sig = inspect.signature(strategy.run)
        params = list(sig.parameters.values())
        for p in params:
            assert p.annotation is not GoldCase, "Strategy.run must not accept GoldCase"

    def test_strategy_logs_metadata(
        self, simple_case: InferenceCase, simple_catalog: DatabaseCatalog
    ) -> None:
        stub = StubLLMClient()
        strategy = FullSchemaStrategy(stub)
        pred = strategy.run(simple_case, simple_catalog)

        assert pred.metadata.get("database_id") == "shop"
        assert pred.metadata.get("prompt_version") == PROMPT_VERSION
        assert "raw_response" in pred.metadata

    def test_strategy_registered(self) -> None:
        """FullSchemaStrategy must be importable and registered."""
        # Import to trigger @register decorator
        import chatsql.strategies.full_schema  # noqa: F401
        from chatsql.experiments.registry import get_strategy

        cls = get_strategy("full_schema")
        assert cls is FullSchemaStrategy

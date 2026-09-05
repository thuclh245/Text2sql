"""Tests for full-schema SQL generation components."""

from __future__ import annotations

import pytest

from chatsql.domain.catalog import ColumnInfo, DatabaseCatalog, TableInfo
from chatsql.domain.inference_case import InferenceCase
from chatsql.generation.llm_client import StubLLMClient
from chatsql.generation.parser import extract_sql
from chatsql.generation.prompt_builder import PROMPT_VERSION, FullSchemaPromptBuilder
from chatsql.generation.token_estimator import estimate_chat_prompt_tokens
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

    def test_schema_qualified_fk_reference_renders_correctly(
        self, simple_case: InferenceCase
    ) -> None:
        """A 3-part schema-qualified reference must render the table/column
        segments, not the schema segment, in the FOREIGN KEY DDL comment."""
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

        builder = FullSchemaPromptBuilder()
        prompt, _ = builder.build(simple_case, catalog)

        assert "FOREIGN KEY (user_id) REFERENCES users(id)" in prompt

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
        assert context.token_estimate > 0

    def test_token_estimator_counts_chat_prompt(self) -> None:
        assert estimate_chat_prompt_tokens("SELECT * FROM products", "gpt-4o-mini") > 4

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
        assert pred.metadata.get("prompt_tokens_estimated") > 0
        assert pred.metadata.get("estimated_total_tokens") >= pred.metadata.get(
            "prompt_tokens_estimated"
        )
        assert "raw_response" in pred.metadata

    def test_strategy_registered(self) -> None:
        """FullSchemaStrategy must be importable and registered."""
        # Import to trigger @register decorator
        import chatsql.strategies.full_schema  # noqa: F401
        from chatsql.experiments.registry import get_strategy

        cls = get_strategy("full_schema")
        assert cls is FullSchemaStrategy


# ---------------------------------------------------------------------------
# LLM payload preview & verbose printing tests
# ---------------------------------------------------------------------------


class TestLLMRequestPayloadFormatting:
    def test_format_llm_request_valid_parameters_returns_formatted_string(self) -> None:
        from chatsql.generation.llm_client import format_llm_request

        preview = format_llm_request(
            model="gpt-4o-mini",
            provider="openai",
            prompt="SELECT * FROM products",
            temperature=0.2,
            max_tokens=256,
        )
        assert "[CHATSQL -> LLM API REQUEST]" in preview
        assert "Provider:    openai" in preview
        assert "Model:       gpt-4o-mini" in preview
        assert "Temperature: 0.2" in preview
        assert "Max Tokens:  256" in preview
        assert "SELECT * FROM products" in preview

    def test_stub_llm_client_verbose_prints_request_payload(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        stub = StubLLMClient(verbose=True)
        stub.complete("SELECT count(*) FROM users")
        captured = capsys.readouterr()
        assert "[CHATSQL -> LLM API REQUEST]" in captured.out
        assert "SELECT count(*) FROM users" in captured.out

    def test_build_llm_client_verbose_flag_passed_to_instance(self) -> None:
        from chatsql.generation.llm_client import build_llm_client

        client = build_llm_client({"provider": "stub", "verbose": True})
        assert client.is_verbose is True


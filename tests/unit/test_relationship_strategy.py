"""Tests for RelationshipAwareStrategy with mock LLM client."""

from __future__ import annotations

from chatsql.domain.catalog import ColumnInfo, DatabaseCatalog, TableInfo
from chatsql.domain.inference_case import InferenceCase
from chatsql.generation.llm_client import BaseLLMClient, LLMResponse
from chatsql.strategies.relationship_aware import RelationshipAwareStrategy


class MockLLMClient(BaseLLMClient):
    @property
    def provider(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return "mock-model"

    @property
    def max_completion_tokens(self) -> int:
        return 512

    def complete(self, prompt: str) -> LLMResponse:
        return LLMResponse(
            raw_text=(
                "```sql\n"
                "SELECT customers.name FROM customers "
                "JOIN orders ON customers.id = orders.customer_id;\n"
                "```"
            ),
            model="mock-model",
            prompt_tokens=50,
            completion_tokens=20,
            latency_seconds=0.1,
        )


def test_relationship_aware_strategy() -> None:
    catalog = DatabaseCatalog(
        database_id="shop",
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
        ),
    )

    case = InferenceCase(
        case_id="case_1",
        question="Find customer names who have placed orders",
        database_id="shop",
    )

    client = MockLLMClient()
    strategy = RelationshipAwareStrategy(client)
    pred = strategy.run(case, catalog)

    assert pred.case_id == "case_1"
    assert "JOIN orders ON customers.id = orders.customer_id" in pred.predicted_sql
    assert "relationship_plan" in pred.metadata
    assert pred.metadata["relationship_plan"]["tables"] == ("customers", "orders")
    assert len(pred.metadata["relationship_plan"]["edges"]) == 1

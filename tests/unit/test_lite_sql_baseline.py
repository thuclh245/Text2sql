"""Unit tests for LitE-SQL baseline adapter, input mapper, output normalizer, and runner."""

from __future__ import annotations

import pytest

from chatsql.baselines.lite_sql.adapter import LiteSqlAdapter
from chatsql.baselines.lite_sql.input_mapper import LiteSqlInputMapper
from chatsql.baselines.lite_sql.output_normalizer import LiteSqlOutputNormalizer
from chatsql.domain.catalog import ColumnInfo, DatabaseCatalog, TableInfo
from chatsql.domain.inference_case import InferenceCase
from chatsql.experiments.registry import get_strategy
from chatsql.generation.llm_client import StubLLMClient
from chatsql.runners.process import ProcessRunner


@pytest.fixture()
def sample_catalog() -> DatabaseCatalog:
    id_col = ColumnInfo(name="id", data_type="INTEGER", is_primary_key=True)
    name_col = ColumnInfo(name="name", data_type="TEXT")
    tbl = TableInfo(name="users", columns=(id_col, name_col))
    return DatabaseCatalog(database_id="test_db", tables=(tbl,))


@pytest.fixture()
def sample_case() -> InferenceCase:
    return InferenceCase(
        case_id="lite_1",
        question="Show all users",
        database_id="test_db",
        evidence={"text": "list users"},
    )


class TestLiteSqlInputMapper:
    def test_to_lite_sql_format(
        self, sample_case: InferenceCase, sample_catalog: DatabaseCatalog
    ) -> None:
        mapper = LiteSqlInputMapper()
        data = mapper.to_lite_sql_format(sample_case, sample_catalog)

        assert data["case_id"] == "lite_1"
        assert data["db_id"] == "test_db"
        assert data["question"] == "Show all users"
        assert data["evidence"] == "list users"
        assert len(data["schema"]) == 1
        assert data["schema"][0]["table_name"] == "users"


class TestLiteSqlOutputNormalizer:
    def test_normalize_dict_input(self) -> None:
        normalizer = LiteSqlOutputNormalizer()
        pred = normalizer.normalize(
            case_id="c1",
            database_id="db1",
            raw_output={"predict_sql": "SELECT * FROM users"},
            latency_seconds=0.5,
        )

        assert pred.case_id == "c1"
        assert pred.predicted_sql == "SELECT * FROM users"
        assert pred.metadata["database_id"] == "db1"
        assert pred.metadata["baseline_system"] == "LitE-SQL"

    def test_normalize_string_input(self) -> None:
        normalizer = LiteSqlOutputNormalizer()
        pred = normalizer.normalize(
            case_id="c2",
            database_id="db2",
            raw_output="```sql\nSELECT COUNT(*) FROM users\n```",
        )

        assert pred.predicted_sql == "SELECT COUNT(*) FROM users"


class TestLiteSqlAdapter:
    def test_adapter_runs_with_stub_client(
        self, sample_case: InferenceCase, sample_catalog: DatabaseCatalog
    ) -> None:
        stub = StubLLMClient("SELECT * FROM users")
        adapter = LiteSqlAdapter(llm_client=stub)
        pred = adapter.run(sample_case, sample_catalog)

        assert pred.case_id == "lite_1"
        assert pred.predicted_sql == "SELECT * FROM users"

    def test_adapter_registered(self) -> None:
        cls = get_strategy("lite-sql")
        assert cls is LiteSqlAdapter


class TestProcessRunner:
    def test_process_runner_executes_echo(self) -> None:
        runner = ProcessRunner()
        code, stdout, stderr = runner.run(["echo", "hello"])

        assert code == 0
        assert "hello" in stdout

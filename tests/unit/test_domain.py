"""Unit tests for domain contracts (P0-T02)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from chatsql.domain.catalog import ColumnInfo, DatabaseCatalog, TableInfo
from chatsql.domain.evidence import Evidence
from chatsql.domain.gold_case import GoldCase
from chatsql.domain.inference_case import InferenceCase
from chatsql.domain.result import ExecutionResult, ExperimentRecord, Prediction

# ---------------------------------------------------------------------------
# InferenceCase
# ---------------------------------------------------------------------------


class TestInferenceCase:
    def test_basic_construction(self) -> None:
        case = InferenceCase(case_id="c1", question="Q?", database_id="db1")
        assert case.case_id == "c1"
        assert case.question == "Q?"
        assert case.database_id == "db1"
        assert case.evidence is None

    def test_with_evidence(self) -> None:
        case = InferenceCase(
            case_id="c2",
            question="How old?",
            database_id="db2",
            evidence={"text": "age > 21 means adult"},
        )
        assert case.evidence is not None
        assert case.evidence["text"] == "age > 21 means adult"

    def test_is_frozen(self) -> None:
        case = InferenceCase(case_id="c1", question="Q?", database_id="db1")
        with pytest.raises((TypeError, ValidationError)):
            case.question = "new"  # type: ignore[misc]

    def test_rejects_extra_fields(self) -> None:
        with pytest.raises((TypeError, ValidationError)):
            InferenceCase(  # type: ignore[call-arg]
                case_id="c1",
                question="Q?",
                database_id="db1",
                gold_sql="SELECT 1",
            )


# ---------------------------------------------------------------------------
# GoldCase
# ---------------------------------------------------------------------------


class TestGoldCase:
    def test_basic_construction(self) -> None:
        gold = GoldCase(case_id="c1", gold_sql="SELECT COUNT(*) FROM t")
        assert gold.gold_sql == "SELECT COUNT(*) FROM t"
        assert gold.gold_tables == ()
        assert gold.gold_columns == ()

    def test_with_tables_and_columns(self) -> None:
        gold = GoldCase(
            case_id="c1",
            gold_sql="SELECT id FROM users",
            gold_tables=("users",),
            gold_columns=("id",),
        )
        assert "users" in gold.gold_tables
        assert "id" in gold.gold_columns

    def test_is_frozen(self) -> None:
        gold = GoldCase(case_id="c1", gold_sql="SELECT 1")
        with pytest.raises((TypeError, ValidationError)):
            gold.gold_sql = "SELECT 2"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


class TestCatalog:
    def _make_catalog(self) -> DatabaseCatalog:
        col1 = ColumnInfo(name="id", data_type="INTEGER", is_primary_key=True)
        col2 = ColumnInfo(name="name", data_type="TEXT")
        table = TableInfo(name="users", columns=(col1, col2))
        return DatabaseCatalog(database_id="mydb", tables=(table,))

    def test_table_names(self) -> None:
        cat = self._make_catalog()
        assert cat.table_names() == ["users"]

    def test_get_table(self) -> None:
        cat = self._make_catalog()
        t = cat.get_table("users")
        assert t is not None
        assert t.column_names() == ["id", "name"]

    def test_get_missing_table(self) -> None:
        cat = self._make_catalog()
        assert cat.get_table("orders") is None

    def test_from_dict(self) -> None:
        data = {
            "database_id": "mydb",
            "tables": [
                {
                    "name": "products",
                    "columns": [{"name": "sku", "data_type": "TEXT"}],
                }
            ],
        }
        cat = DatabaseCatalog.from_dict(data)
        assert cat.database_id == "mydb"
        assert cat.table_names() == ["products"]


# ---------------------------------------------------------------------------
# Prediction / ExecutionResult / ExperimentRecord
# ---------------------------------------------------------------------------


class TestResultTypes:
    def test_prediction_basic(self) -> None:
        pred = Prediction(case_id="c1", predicted_sql="SELECT 1")
        assert pred.predicted_sql == "SELECT 1"
        assert pred.latency_seconds is None

    def test_prediction_frozen(self) -> None:
        pred = Prediction(case_id="c1", predicted_sql="SELECT 1")
        with pytest.raises((TypeError, ValidationError)):
            pred.predicted_sql = "SELECT 2"  # type: ignore[misc]

    def test_execution_result_error(self) -> None:
        er = ExecutionResult(case_id="c1", executed=False, error="syntax error")
        assert not er.executed
        assert er.error == "syntax error"

    def test_experiment_record_defaults(self) -> None:
        rec = ExperimentRecord(
            case_id="c1",
            database_id="db1",
            question="Q?",
            predicted_sql="SELECT 1",
            executed=True,
            execution_correct=True,
        )
        assert rec.execution_correct is True
        assert rec.timestamp is not None


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------


class TestEvidence:
    def test_basic(self) -> None:
        ev = Evidence(text="age > 18 means adult")
        assert ev.text == "age > 18 means adult"
        assert ev.metadata == {}

    def test_with_metadata(self) -> None:
        ev = Evidence(text="hint", metadata={"source": "BIRD"})
        assert ev.metadata["source"] == "BIRD"

    def test_frozen(self) -> None:
        ev = Evidence(text="hint")
        with pytest.raises((TypeError, ValidationError)):
            ev.text = "changed"  # type: ignore[misc]

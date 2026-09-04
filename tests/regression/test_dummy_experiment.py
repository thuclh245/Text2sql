"""Regression / integration test: dummy experiment produces complete artifact tree.

This test satisfies the foundation exit gate requirement:
    "A dummy experiment creates sufficient artifacts."
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from chatsql.domain.catalog import ColumnInfo, DatabaseCatalog, TableInfo
from chatsql.domain.gold_case import GoldCase
from chatsql.domain.inference_case import InferenceCase
from chatsql.domain.result import Prediction
from chatsql.execution import ReadOnlySQLiteExecutor
from chatsql.experiments.logger import RunLogger
from chatsql.experiments.manifest import build_manifest
from chatsql.experiments.runner import BaseEvaluator, BaseStrategy, ExperimentRunner
from chatsql.grounding import ColumnRef, GroundingResult, SchemaGrounder, TableRef

# ---------------------------------------------------------------------------
# Minimal concrete implementations for testing
# ---------------------------------------------------------------------------


class DummyStrategy(BaseStrategy):
    """Generates a trivial SELECT query for every case."""

    def run(self, case: InferenceCase, catalog: DatabaseCatalog) -> Prediction:
        tables = catalog.table_names()
        sql = f"SELECT * FROM {tables[0]}" if tables else "SELECT 1"
        return Prediction(case_id=case.case_id, predicted_sql=sql, latency_seconds=0.001)


class DummyEvaluator(BaseEvaluator):
    """Reports correctness straight from the execution flag (no gold DB in this test)."""

    def evaluate(
        self,
        prediction: Prediction,
        execution: Any,
        gold_sql: str,
        gold_tables: tuple[str, ...],
        gold_columns: tuple[str, ...],
    ) -> dict[str, Any]:
        return {"execution_correct": execution.executed}


class OrdersOnlyGrounder(SchemaGrounder):
    """Selects only the orders table so the runner projection can be asserted."""

    def ground(self, case: InferenceCase, catalog: DatabaseCatalog) -> GroundingResult:
        return GroundingResult(
            tables=(TableRef(name="orders"),),
            columns=(ColumnRef(table_name="orders", column_name="id"),),
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def simple_catalog() -> DatabaseCatalog:
    col = ColumnInfo(name="id", data_type="INTEGER", is_primary_key=True)
    table = TableInfo(name="orders", columns=(col,))
    return DatabaseCatalog(database_id="shop", tables=(table,))


@pytest.fixture()
def cases_and_golds() -> tuple[list[InferenceCase], list[GoldCase]]:
    cases = [
        InferenceCase(case_id=f"q{i}", question=f"Question {i}", database_id="shop")
        for i in range(3)
    ]
    golds = [GoldCase(case_id=f"q{i}", gold_sql=f"SELECT {i} FROM orders") for i in range(3)]
    return cases, golds


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


class TestDummyExperiment:
    def test_dummy_experiment_creates_complete_artifact_tree(
        self,
        tmp_path: Path,
        simple_catalog: DatabaseCatalog,
        cases_and_golds: tuple,
    ) -> None:
        cases, golds = cases_and_golds
        run_id = "foundation_dummy_run"

        manifest = build_manifest(
            experiment_id=run_id,
            seed=0,
            benchmark_name="BIRD-mini-dev",
            benchmark_revision="test",
            benchmark_data_hash="0" * 64,
            evaluator_revision="test",
            strategy_name="DummyStrategy",
            strategy_config={"dummy": True},
            model_provider="stub",
            model_name="stub-model",
            model_revision="v0",
            model_temperature=0.0,
        )

        logger = RunLogger(runs_root=tmp_path, run_id=run_id)
        runner = ExperimentRunner(
            strategy=DummyStrategy(),
            evaluator=DummyEvaluator(),
            logger=logger,
            executor=ReadOnlySQLiteExecutor(tmp_path),
        )

        catalogs = {"shop": simple_catalog}
        records = runner.run(manifest=manifest, cases=cases, golds=golds, catalogs=catalogs)

        # All 3 cases should produce records
        assert len(records) == 3

        # The standard artifact files must exist
        assert logger.is_complete(), (
            "Dummy experiment must create: manifest.json, predictions.jsonl, "
            "context_views.jsonl, raw_model_outputs.jsonl, executions.jsonl, "
            "metrics.json, errors.jsonl"
        )

    def test_manifest_captured_in_run(
        self,
        tmp_path: Path,
        simple_catalog: DatabaseCatalog,
    ) -> None:
        """manifest.json must contain the experiment ID."""
        run_id = "manifest-capture-test"
        manifest = build_manifest(
            experiment_id=run_id,
            seed=7,
            benchmark_name="BIRD",
            benchmark_revision="test",
            benchmark_data_hash="h",
            evaluator_revision="e",
            strategy_name="Dummy",
            model_provider="stub",
            model_name="stub",
            model_revision="v0",
            model_temperature=0.0,
        )

        cases = [InferenceCase(case_id="q0", question="How many?", database_id="shop")]
        golds = [GoldCase(case_id="q0", gold_sql="SELECT COUNT(*) FROM orders")]

        logger = RunLogger(runs_root=tmp_path, run_id=run_id)
        runner = ExperimentRunner(
            strategy=DummyStrategy(),
            evaluator=DummyEvaluator(),
            logger=logger,
            executor=ReadOnlySQLiteExecutor(tmp_path),
        )
        runner.run(manifest=manifest, cases=cases, golds=golds, catalogs={"shop": simple_catalog})

        manifest_data = json.loads((tmp_path / run_id / "manifest.json").read_text())
        assert manifest_data["experiment"]["id"] == run_id
        assert manifest_data["experiment"]["seed"] == 7
        assert manifest_data["benchmark"]["name"] == "BIRD"

    def test_case_gold_mismatch_fails_fast(
        self,
        tmp_path: Path,
        simple_catalog: DatabaseCatalog,
    ) -> None:
        manifest = build_manifest(
            experiment_id="mismatch-test",
            seed=0,
            benchmark_name="BIRD",
            benchmark_revision="test",
            benchmark_data_hash="h",
            evaluator_revision="e",
            strategy_name="Dummy",
            model_provider="stub",
            model_name="stub",
            model_revision="v0",
            model_temperature=0.0,
        )
        runner = ExperimentRunner(
            strategy=DummyStrategy(),
            evaluator=DummyEvaluator(),
            logger=RunLogger(runs_root=tmp_path, run_id="mismatch-test"),
            executor=ReadOnlySQLiteExecutor(tmp_path),
        )

        with pytest.raises(ValueError, match="case/gold mismatch"):
            runner.run(
                manifest=manifest,
                cases=[InferenceCase(case_id="q0", question="Q?", database_id="shop")],
                golds=[GoldCase(case_id="q1", gold_sql="SELECT 1")],
                catalogs={"shop": simple_catalog},
            )

    def test_strategy_failure_still_emits_record(
        self,
        tmp_path: Path,
        simple_catalog: DatabaseCatalog,
    ) -> None:
        class FailingStrategy(BaseStrategy):
            def run(self, case: InferenceCase, catalog: DatabaseCatalog) -> Prediction:
                raise RuntimeError("boom")

        manifest = build_manifest(
            experiment_id="failure-record-test",
            seed=0,
            benchmark_name="BIRD",
            benchmark_revision="test",
            benchmark_data_hash="h",
            evaluator_revision="e",
            strategy_name="Failing",
            model_provider="stub",
            model_name="stub",
            model_revision="v0",
            model_temperature=0.0,
        )
        logger = RunLogger(runs_root=tmp_path, run_id="failure-record-test")
        runner = ExperimentRunner(
            strategy=FailingStrategy(),
            evaluator=DummyEvaluator(),
            logger=logger,
            executor=ReadOnlySQLiteExecutor(tmp_path),
        )

        records = runner.run(
            manifest=manifest,
            cases=[InferenceCase(case_id="q0", question="Q?", database_id="shop")],
            golds=[GoldCase(case_id="q0", gold_sql="SELECT 1")],
            catalogs={"shop": simple_catalog},
        )

        assert len(records) == 1
        assert records[0].case_id == "q0"
        assert records[0].executed is False
        assert records[0].execution_correct is False
        assert records[0].error == "boom"

        metrics = json.loads((tmp_path / "failure-record-test" / "metrics.json").read_text())
        assert metrics["total"] == 1
        assert metrics["errors"] == 1

    def test_runner_uses_grounded_catalog(
        self,
        tmp_path: Path,
        simple_catalog: DatabaseCatalog,
    ) -> None:
        class CapturingStrategy(BaseStrategy):
            def __init__(self) -> None:
                self.seen_catalog: DatabaseCatalog | None = None

            def run(self, case: InferenceCase, catalog: DatabaseCatalog) -> Prediction:
                self.seen_catalog = catalog
                return Prediction(case_id=case.case_id, predicted_sql="SELECT 1")

        manifest = build_manifest(
            experiment_id="grounded-catalog-test",
            seed=0,
            benchmark_name="BIRD",
            benchmark_revision="test",
            benchmark_data_hash="h",
            evaluator_revision="e",
            strategy_name="Grounded",
            model_provider="stub",
            model_name="stub",
            model_revision="v0",
            model_temperature=0.0,
        )
        strategy = CapturingStrategy()
        runner = ExperimentRunner(
            strategy=strategy,
            evaluator=DummyEvaluator(),
            logger=RunLogger(runs_root=tmp_path, run_id="grounded-catalog-test"),
            executor=ReadOnlySQLiteExecutor(tmp_path),
            grounder=OrdersOnlyGrounder(),
        )

        records = runner.run(
            manifest=manifest,
            cases=[InferenceCase(case_id="q0", question="Q?", database_id="shop")],
            golds=[
                GoldCase(
                    case_id="q0",
                    gold_sql="SELECT id FROM orders",
                    gold_tables=("orders",),
                    gold_columns=("id",),
                )
            ],
            catalogs={"shop": simple_catalog},
        )

        assert strategy.seen_catalog is not None
        assert strategy.seen_catalog.table_names() == ["orders"]
        assert strategy.seen_catalog.tables[0].column_names() == ["id"]
        assert records[0].metadata["retrieval"]["table_recall"] == 1.0

"""Unit tests for run logging artifacts."""

from __future__ import annotations

import datetime
import json
from pathlib import Path

import pytest

from chatsql.experiments.logger import RunLogger
from chatsql.experiments.manifest import (
    BenchmarkMeta,
    EnvironmentMeta,
    ExperimentManifest,
    ExperimentMeta,
    ModelMeta,
    SystemMeta,
)


def _make_manifest(run_id: str) -> ExperimentManifest:
    return ExperimentManifest(
        experiment=ExperimentMeta(
            id=run_id,
            timestamp=datetime.datetime(2026, 1, 1),
            seed=1,
            git_commit="abc",
        ),
        benchmark=BenchmarkMeta(
            name="BIRD", revision="v1", data_hash="h1", evaluator_revision="ev1"
        ),
        system=SystemMeta(strategy="Dummy", config_hash="ch", upstream_commit="unknown"),
        model=ModelMeta(provider="openai", name="gpt-4o-mini", revision="r1", temperature=0.0),
        environment=EnvironmentMeta(python="3.11", os="Linux", dependency_lock_hash="lh"),
    )


class TestRunLogger:
    def test_logger_creates_complete_run_directory(self, tmp_path: Path) -> None:
        """RunLogger must create all 5 required artifact files."""
        run_id = "run-test-001"
        logger = RunLogger(runs_root=tmp_path, run_id=run_id)
        manifest = _make_manifest(run_id)

        logger.write_manifest(manifest)
        logger.log_prediction({"case_id": "c1", "predicted_sql": "SELECT 1"})
        logger.log_execution({"case_id": "c1", "executed": False, "error": "stub"})
        logger.log_error({"case_id": "c2", "component": "strategy", "error": "timeout"})
        logger.write_metrics({"total": 1, "executed": 0, "errors": 1})

        assert logger.is_complete(), "RunLogger must create all 5 artifact files"

    def test_run_directory_structure(self, tmp_path: Path) -> None:
        run_id = "run-struct-001"
        logger = RunLogger(runs_root=tmp_path, run_id=run_id)
        manifest = _make_manifest(run_id)

        logger.write_manifest(manifest)
        logger.log_prediction({"case_id": "c1", "predicted_sql": "SELECT 1"})
        logger.log_execution({"case_id": "c1", "executed": False})
        logger.log_error({"case_id": "c1", "error": "none"})
        logger.write_metrics({"total": 1})

        run_dir = tmp_path / run_id
        assert (run_dir / "manifest.json").exists()
        assert (run_dir / "predictions.jsonl").exists()
        assert (run_dir / "executions.jsonl").exists()
        assert (run_dir / "errors.jsonl").exists()
        assert (run_dir / "metrics.json").exists()

    def test_manifest_json_roundtrip(self, tmp_path: Path) -> None:
        run_id = "run-json-001"
        logger = RunLogger(runs_root=tmp_path, run_id=run_id)
        manifest = _make_manifest(run_id)
        logger.write_manifest(manifest)

        text = (tmp_path / run_id / "manifest.json").read_text()
        data = json.loads(text)
        assert data["experiment"]["id"] == run_id
        assert data["benchmark"]["name"] == "BIRD"

    def test_predictions_jsonl_is_valid(self, tmp_path: Path) -> None:
        logger = RunLogger(runs_root=tmp_path, run_id="run-pred-001")
        for i in range(3):
            logger.log_prediction({"case_id": f"c{i}", "predicted_sql": f"SELECT {i}"})

        lines = (tmp_path / "run-pred-001" / "predictions.jsonl").read_text().splitlines()
        assert len(lines) == 3
        for line in lines:
            rec = json.loads(line)
            assert "case_id" in rec

    def test_metrics_json_valid(self, tmp_path: Path) -> None:
        logger = RunLogger(runs_root=tmp_path, run_id="run-metrics-001")
        metrics = {"total": 100, "executed": 80, "errors": 5, "ex_accuracy": 0.72}
        logger.write_metrics(metrics)

        text = (tmp_path / "run-metrics-001" / "metrics.json").read_text()
        loaded = json.loads(text)
        assert loaded["total"] == 100
        assert loaded["ex_accuracy"] == pytest.approx(0.72)

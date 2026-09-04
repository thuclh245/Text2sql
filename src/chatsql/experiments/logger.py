"""RunLogger — writes the standard run directory artifact tree.

Output layout:
    runs/<run_id>/
    ├── manifest.json
    ├── predictions.jsonl
    ├── context_views.jsonl
    ├── groundings.jsonl
    ├── raw_model_outputs.jsonl
    ├── executions.jsonl
    ├── metrics.json
    └── errors.jsonl
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from chatsql.experiments.manifest import ExperimentManifest


class RunLogger:
    """Manages the output directory for a single experiment run."""

    def __init__(self, runs_root: Path, run_id: str) -> None:
        self.run_dir: Path = runs_root / run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)

        self._predictions_path = self.run_dir / "predictions.jsonl"
        self._context_views_path = self.run_dir / "context_views.jsonl"
        self._groundings_path = self.run_dir / "groundings.jsonl"
        self._raw_outputs_path = self.run_dir / "raw_model_outputs.jsonl"
        self._executions_path = self.run_dir / "executions.jsonl"
        self._errors_path = self.run_dir / "errors.jsonl"
        for path in (
            self._predictions_path,
            self._context_views_path,
            self._groundings_path,
            self._raw_outputs_path,
            self._executions_path,
            self._errors_path,
        ):
            path.touch(exist_ok=True)

    # ------------------------------------------------------------------
    # Manifest
    # ------------------------------------------------------------------

    def write_manifest(self, manifest: ExperimentManifest) -> None:
        """Serialise manifest to manifest.json (deterministic, sorted keys)."""
        path = self.run_dir / "manifest.json"
        path.write_text(manifest.to_json(), encoding="utf-8")

    # ------------------------------------------------------------------
    # Streaming writers (append one record per call)
    # ------------------------------------------------------------------

    def log_prediction(self, record: dict[str, Any]) -> None:
        """Append one prediction record to predictions.jsonl."""
        self._append_jsonl(self._predictions_path, record)

    def log_context_view(self, record: dict[str, Any]) -> None:
        """Append one rendered LLM context to context_views.jsonl."""
        self._append_jsonl(self._context_views_path, record)

    def log_grounding(self, record: dict[str, Any]) -> None:
        """Append one schema grounding result to groundings.jsonl."""
        self._append_jsonl(self._groundings_path, record)

    def log_raw_output(self, record: dict[str, Any]) -> None:
        """Append one raw model response to raw_model_outputs.jsonl (for auditing)."""
        self._append_jsonl(self._raw_outputs_path, record)

    def log_execution(self, record: dict[str, Any]) -> None:
        """Append one execution record to executions.jsonl."""
        self._append_jsonl(self._executions_path, record)

    def log_error(self, record: dict[str, Any]) -> None:
        """Append one error record to errors.jsonl."""
        self._append_jsonl(self._errors_path, record)

    # ------------------------------------------------------------------
    # Metrics (written once at end of run)
    # ------------------------------------------------------------------

    def write_metrics(self, metrics: dict[str, Any]) -> None:
        """Write final aggregated metrics to metrics.json."""
        path = self.run_dir / "metrics.json"
        path.write_text(json.dumps(metrics, sort_keys=True, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------
    # Completeness check
    # ------------------------------------------------------------------

    def is_complete(self) -> bool:
        """Return True if all required files exist in the run directory."""
        required = [
            "manifest.json",
            "predictions.jsonl",
            "context_views.jsonl",
            "groundings.jsonl",
            "raw_model_outputs.jsonl",
            "executions.jsonl",
            "metrics.json",
            "errors.jsonl",
        ]
        return all((self.run_dir / f).exists() for f in required)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

"""Ablation gate report for relationship-aware join reasoning."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from chatsql.analysis.reports import analyze_run_directory

RELATIONSHIP_METRIC_KEYS = (
    "relationship_total",
    "relationship_edge_recall",
    "relationship_edge_precision",
    "relationship_wrong_edge_rate",
    "relationship_path_coverage",
    "relationship_exact_path_accuracy",
    "relationship_mean_hop_count",
)

TARGET_SLICE_CANDIDATES: dict[str, tuple[tuple[str | None, str], ...]] = {
    "A1": (
        (None, "multiple_fk_ambiguity"),
        ("join_relationship", "multiple_fk_ambiguity"),
    ),
    "A2": (
        (None, "grain_sensitive_aggregation"),
        (None, "fanout_aggregation"),
        (None, "aggregation_query"),
        ("join_depth", "2+_joins"),
        ("table_slice", "multi_table"),
    ),
    "A3": (
        (None, "bridge_table_required"),
        ("join_relationship", "bridge_table_required"),
    ),
}


def generate_relationship_ablation_gate_report(
    relationship_aware_run_dir: Path,
    a1_run_dir: Path,
    a2_run_dir: Path,
    a3_run_dir: Path,
    relationship_aware_name: str = "relationship_aware",
    a1_name: str = "A1_no_role_disambiguation",
    a2_name: str = "A2_no_grain_validation",
    a3_name: str = "A3_no_bridge_expansion",
    targeted_drop_threshold_pct: float = 5.0,
) -> dict[str, Any]:
    """Compare relationship-aware runs against A1/A2/A3 ablations."""
    relationship_summary = _load_or_analyze_summary(relationship_aware_run_dir)
    relationship_metrics = _load_run_metrics(relationship_aware_run_dir)

    ablation_specs = (
        ("A1", a1_name, a1_run_dir),
        ("A2", a2_name, a2_run_dir),
        ("A3", a3_name, a3_run_dir),
    )
    ablations: list[dict[str, Any]] = []

    for ablation_id, ablation_name, ablation_run_dir in ablation_specs:
        ablation_summary = _load_or_analyze_summary(ablation_run_dir)
        ablation_metrics = _load_run_metrics(ablation_run_dir)
        slice_deltas = _compute_slice_accuracy_deltas(
            _dict_value(relationship_summary, "slices"),
            _dict_value(ablation_summary, "slices"),
        )
        target_slice = _find_target_slice_delta(
            slice_deltas,
            TARGET_SLICE_CANDIDATES[ablation_id],
        )
        target_drop_pct = (
            round(-target_slice["accuracy_delta_pct"], 2) if target_slice is not None else 0.0
        )
        target_gate_passed = (
            target_slice is not None
            and target_slice["relationship_aware_total"] > 0
            and target_slice["ablation_total"] > 0
            and target_drop_pct >= targeted_drop_threshold_pct
        )

        ablations.append(
            {
                "ablation_id": ablation_id,
                "ablation_name": ablation_name,
                "run_dir": str(ablation_run_dir),
                "overall": _compute_accuracy_delta(relationship_summary, ablation_summary),
                "target_slice": target_slice,
                "target_drop_pct": target_drop_pct,
                "targeted_drop_threshold_pct": targeted_drop_threshold_pct,
                "slice_deltas": slice_deltas,
                "relationship_metrics": _compute_metric_deltas(
                    relationship_metrics,
                    ablation_metrics,
                    RELATIONSHIP_METRIC_KEYS,
                ),
                "gate": {
                    "targeted_slice_drop_detected": target_gate_passed,
                    "passed": target_gate_passed,
                },
            }
        )

    return {
        "phase": "7B",
        "relationship_aware_name": relationship_aware_name,
        "relationship_aware_run_dir": str(relationship_aware_run_dir),
        "targeted_drop_threshold_pct": targeted_drop_threshold_pct,
        "ablations": ablations,
        "gate": {
            "all_targeted_drops_detected": all(
                ablation["gate"]["targeted_slice_drop_detected"]
                for ablation in ablations
            ),
            "passed": all(ablation["gate"]["passed"] for ablation in ablations),
        },
    }


def format_relationship_ablation_gate_report_md(report: dict[str, Any]) -> str:
    """Render a relationship ablation gate report as Markdown."""
    gate = report["gate"]
    status = "PASS" if gate["passed"] else "FAIL"

    lines: list[str] = [
        "# Phase 7B Ablation Gate Report",
        "",
        f"- **Full relationship-aware system:** `{report['relationship_aware_name']}` "
        f"({report['relationship_aware_run_dir']})",
        f"- **Targeted drop threshold:** {report['targeted_drop_threshold_pct']:.2f}pp",
        f"- **Gate Status:** **{status}**",
        "",
        "## Targeted Drops",
        "| Ablation | Target Slice | Relationship Aware | Ablation | Drop | Passed |",
        "|---|---|---:|---:|---:|:---:|",
    ]

    for ablation in report["ablations"]:
        target = ablation["target_slice"]
        if target is None:
            lines.append(
                f"| `{ablation['ablation_id']}` {ablation['ablation_name']} | "
                "not found | 0.00 | 0.00 | +0.00 | no |"
            )
            continue

        target_label = f"{target['slice_dimension']}={target['slice_value']}"
        lines.append(
            f"| `{ablation['ablation_id']}` {ablation['ablation_name']} | "
            f"`{target_label}` | "
            f"{target['relationship_aware_accuracy_pct']:.2f} | "
            f"{target['ablation_accuracy_pct']:.2f} | "
            f"{ablation['target_drop_pct']:+.2f} | "
            f"{_yes_no(ablation['gate']['targeted_slice_drop_detected'])} |"
        )

    lines.extend(
        [
            "",
            "## Overall EX",
            "| Ablation | Relationship Aware | Ablation | Delta | Cases |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for ablation in report["ablations"]:
        overall = ablation["overall"]
        lines.append(
            f"| `{ablation['ablation_id']}` {ablation['ablation_name']} | "
            f"{overall['relationship_aware_accuracy_pct']:.2f} | "
            f"{overall['ablation_accuracy_pct']:.2f} | "
            f"{overall['accuracy_delta_pct']:+.2f} | "
            f"{overall['relationship_aware_total']} / {overall['ablation_total']} |"
        )

    lines.extend(
        [
            "",
            "## Relationship Metrics",
            "| Ablation | Metric | Relationship Aware | Ablation | Delta |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for ablation in report["ablations"]:
        for metric in ablation["relationship_metrics"]:
            lines.append(
                f"| `{ablation['ablation_id']}` | `{metric['metric']}` | "
                f"{metric['relationship_aware']} | {metric['ablation']} | "
                f"{metric['delta']:+.4f} |"
            )

    return "\n".join(lines) + "\n"


def save_relationship_ablation_gate_report(
    report: dict[str, Any],
    output_dir: Path,
) -> None:
    """Save relationship ablation gate report as JSON and Markdown."""
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "relationship_ablation_gate_report.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    (output_dir / "relationship_ablation_gate_report.md").write_text(
        format_relationship_ablation_gate_report_md(report),
        encoding="utf-8",
    )


def _load_or_analyze_summary(run_dir: Path) -> dict[str, Any]:
    summary_path = run_dir / "error_analysis" / "summary.json"
    if summary_path.exists():
        return _read_json_object(summary_path)
    return analyze_run_directory(run_dir)


def _load_run_metrics(run_dir: Path) -> dict[str, Any]:
    metrics_path = run_dir / "metrics.json"
    if not metrics_path.exists():
        return {}
    return _read_json_object(metrics_path)


def _compute_accuracy_delta(
    relationship_aware_summary: dict[str, Any],
    ablation_summary: dict[str, Any],
) -> dict[str, Any]:
    relationship_accuracy = float(relationship_aware_summary.get("accuracy_pct", 0.0))
    ablation_accuracy = float(ablation_summary.get("accuracy_pct", 0.0))
    return {
        "relationship_aware_total": int(relationship_aware_summary.get("total_cases", 0)),
        "ablation_total": int(ablation_summary.get("total_cases", 0)),
        "relationship_aware_correct": int(relationship_aware_summary.get("correct_cases", 0)),
        "ablation_correct": int(ablation_summary.get("correct_cases", 0)),
        "relationship_aware_accuracy_pct": relationship_accuracy,
        "ablation_accuracy_pct": ablation_accuracy,
        "accuracy_delta_pct": round(ablation_accuracy - relationship_accuracy, 2),
    }


def _compute_slice_accuracy_deltas(
    relationship_aware_slices: dict[str, Any],
    ablation_slices: dict[str, Any],
) -> list[dict[str, Any]]:
    deltas: list[dict[str, Any]] = []
    dimensions = sorted(set(relationship_aware_slices) | set(ablation_slices))
    for dimension in dimensions:
        relationship_values = relationship_aware_slices.get(dimension, {})
        ablation_values = ablation_slices.get(dimension, {})
        if not isinstance(relationship_values, dict) or not isinstance(ablation_values, dict):
            continue

        slice_values = sorted(set(relationship_values) | set(ablation_values))
        for slice_value in slice_values:
            relationship_stats = relationship_values.get(slice_value, {})
            ablation_stats = ablation_values.get(slice_value, {})
            if not isinstance(relationship_stats, dict) or not isinstance(ablation_stats, dict):
                continue

            relationship_accuracy = float(relationship_stats.get("accuracy_pct", 0.0))
            ablation_accuracy = float(ablation_stats.get("accuracy_pct", 0.0))
            deltas.append(
                {
                    "slice_dimension": dimension,
                    "slice_value": slice_value,
                    "relationship_aware_total": int(relationship_stats.get("total", 0)),
                    "ablation_total": int(ablation_stats.get("total", 0)),
                    "relationship_aware_correct": int(relationship_stats.get("correct", 0)),
                    "ablation_correct": int(ablation_stats.get("correct", 0)),
                    "relationship_aware_accuracy_pct": relationship_accuracy,
                    "ablation_accuracy_pct": ablation_accuracy,
                    "accuracy_delta_pct": round(ablation_accuracy - relationship_accuracy, 2),
                }
            )
    return deltas


def _compute_metric_deltas(
    relationship_aware_metrics: dict[str, Any],
    ablation_metrics: dict[str, Any],
    metric_keys: tuple[str, ...],
) -> list[dict[str, Any]]:
    deltas: list[dict[str, Any]] = []
    for key in metric_keys:
        relationship_value = float(relationship_aware_metrics.get(key, 0.0) or 0.0)
        ablation_value = float(ablation_metrics.get(key, 0.0) or 0.0)
        deltas.append(
            {
                "metric": key,
                "relationship_aware": relationship_value,
                "ablation": ablation_value,
                "delta": round(ablation_value - relationship_value, 4),
            }
        )
    return deltas


def _find_target_slice_delta(
    slice_deltas: list[dict[str, Any]],
    candidates: tuple[tuple[str | None, str], ...],
) -> dict[str, Any] | None:
    for candidate_dimension, candidate_value in candidates:
        for delta in slice_deltas:
            dimension_matches = (
                candidate_dimension is None or delta["slice_dimension"] == candidate_dimension
            )
            if dimension_matches and delta["slice_value"] == candidate_value:
                return delta
    return None


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _read_json_object(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return cast(dict[str, Any], data)


def _dict_value(source: dict[str, Any], key: str) -> dict[str, Any]:
    value = source.get(key, {})
    if not isinstance(value, dict):
        return {}
    return cast(dict[str, Any], value)

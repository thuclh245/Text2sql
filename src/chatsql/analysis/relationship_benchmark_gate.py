"""Benchmark gate report for relationship-aware join reasoning."""

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

JOIN_SLICE_NAMES = (
    "1_hop_join",
    "2_hop_join",
    "3_plus_hop_join",
    "multiple_fk_ambiguity",
    "bridge_table_required",
)


def generate_relationship_benchmark_gate_report(
    full_schema_run_dir: Path,
    relationship_aware_run_dir: Path,
    full_schema_name: str = "full_schema",
    relationship_aware_name: str = "relationship_aware",
) -> dict[str, Any]:
    """Compare the full-schema control and relationship-aware run."""
    full_schema_summary = _load_or_analyze_summary(full_schema_run_dir)
    relationship_aware_summary = _load_or_analyze_summary(relationship_aware_run_dir)
    full_schema_metrics = _load_run_metrics(full_schema_run_dir)
    relationship_aware_metrics = _load_run_metrics(relationship_aware_run_dir)

    overall = _compute_accuracy_delta(full_schema_summary, relationship_aware_summary)
    slice_deltas = _compute_slice_accuracy_deltas(
        _dict_value(full_schema_summary, "slices"),
        _dict_value(relationship_aware_summary, "slices"),
    )
    relationship_metric_deltas = _compute_metric_deltas(
        full_schema_metrics,
        relationship_aware_metrics,
        RELATIONSHIP_METRIC_KEYS,
    )

    single_table_delta = _find_slice_delta(slice_deltas, "table_slice", "single_table")
    if single_table_delta is None:
        single_table_delta = _find_slice_delta(slice_deltas, "join_depth", "0_joins")

    join_slice_deltas = [
        delta
        for delta in slice_deltas
        if delta["slice_value"] in JOIN_SLICE_NAMES
        or (
            delta["slice_dimension"] == "table_slice"
            and delta["slice_value"] == "multi_table"
        )
        or (
            delta["slice_dimension"] == "join_depth"
            and delta["slice_value"] != "0_joins"
        )
    ]

    improved_join_slices = [
        delta
        for delta in join_slice_deltas
        if delta["full_schema_total"] > 0
        and delta["relationship_aware_total"] > 0
        and delta["accuracy_delta_pct"] > 0
    ]
    join_gate_passed = bool(improved_join_slices)
    single_table_gate_passed = (
        single_table_delta is None or single_table_delta["accuracy_delta_pct"] >= -1.0
    )
    relationship_gate_passed = _relationship_gate_passed(relationship_metric_deltas)

    return {
        "phase": "7A",
        "full_schema_name": full_schema_name,
        "relationship_aware_name": relationship_aware_name,
        "full_schema_run_dir": str(full_schema_run_dir),
        "relationship_aware_run_dir": str(relationship_aware_run_dir),
        "overall": overall,
        "slice_deltas": slice_deltas,
        "join_slice_deltas": join_slice_deltas,
        "single_table_delta": single_table_delta,
        "relationship_metrics": relationship_metric_deltas,
        "gate": {
            "join_slices_improved": join_gate_passed,
            "single_table_regression_within_tolerance": single_table_gate_passed,
            "relationship_metrics_improved": relationship_gate_passed,
            "passed": join_gate_passed
            and single_table_gate_passed
            and relationship_gate_passed,
        },
    }


def format_relationship_benchmark_gate_report_md(report: dict[str, Any]) -> str:
    """Render a relationship benchmark gate report as Markdown."""
    overall = report["overall"]
    gate = report["gate"]
    status = "PASS" if gate["passed"] else "FAIL"

    lines: list[str] = [
        "# Phase 7A Benchmark Gate Report",
        "",
        f"- **Full-schema control:** `{report['full_schema_name']}` "
        f"({report['full_schema_run_dir']})",
        f"- **Relationship-aware candidate:** `{report['relationship_aware_name']}` "
        f"({report['relationship_aware_run_dir']})",
        f"- **Gate Status:** **{status}**",
        "",
        "## Overall EX",
        "| System | Total | Correct | EX (%) |",
        "|---|---:|---:|---:|",
        (
            f"| {report['full_schema_name']} | {overall['full_schema_total']} | "
            f"{overall['full_schema_correct']} | {overall['full_schema_accuracy_pct']:.2f} |"
        ),
        (
            f"| {report['relationship_aware_name']} | "
            f"{overall['relationship_aware_total']} | "
            f"{overall['relationship_aware_correct']} | "
            f"{overall['relationship_aware_accuracy_pct']:.2f} |"
        ),
        f"| Delta |  |  | {overall['accuracy_delta_pct']:+.2f} |",
        "",
        "## Gate Criteria",
        "| Criterion | Passed |",
        "|---|:---:|",
        f"| Join-heavy slice EX improves | {_yes_no(gate['join_slices_improved'])} |",
        (
            "| Single-table regression within < 1.0% tolerance | "
            f"{_yes_no(gate['single_table_regression_within_tolerance'])} |"
        ),
        (
            "| Relationship metrics improve | "
            f"{_yes_no(gate['relationship_metrics_improved'])} |"
        ),
        "",
        "## Slice EX",
        "| Slice Dimension | Slice | Full Schema | Relationship Aware | Delta | Cases |",
        "|---|---|---:|---:|---:|---:|",
    ]

    for delta in report["slice_deltas"]:
        lines.append(
            f"| `{delta['slice_dimension']}` | `{delta['slice_value']}` | "
            f"{delta['full_schema_accuracy_pct']:.2f} | "
            f"{delta['relationship_aware_accuracy_pct']:.2f} | "
            f"{delta['accuracy_delta_pct']:+.2f} | "
            f"{delta['full_schema_total']} / {delta['relationship_aware_total']} |"
        )

    lines.extend(
        [
            "",
            "## Relationship Metrics",
            "| Metric | Full Schema | Relationship Aware | Delta |",
            "|---|---:|---:|---:|",
        ]
    )
    for metric in report["relationship_metrics"]:
        lines.append(
            f"| `{metric['metric']}` | {metric['full_schema']} | "
            f"{metric['relationship_aware']} | {metric['delta']:+.4f} |"
        )

    return "\n".join(lines) + "\n"


def save_relationship_benchmark_gate_report(
    report: dict[str, Any],
    output_dir: Path,
) -> None:
    """Save relationship benchmark gate report as JSON and Markdown."""
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "relationship_benchmark_gate_report.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    (output_dir / "relationship_benchmark_gate_report.md").write_text(
        format_relationship_benchmark_gate_report_md(report),
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
    full_schema_summary: dict[str, Any],
    relationship_aware_summary: dict[str, Any],
) -> dict[str, Any]:
    full_schema_accuracy = float(full_schema_summary.get("accuracy_pct", 0.0))
    relationship_aware_accuracy = float(relationship_aware_summary.get("accuracy_pct", 0.0))
    return {
        "full_schema_total": int(full_schema_summary.get("total_cases", 0)),
        "relationship_aware_total": int(relationship_aware_summary.get("total_cases", 0)),
        "full_schema_correct": int(full_schema_summary.get("correct_cases", 0)),
        "relationship_aware_correct": int(relationship_aware_summary.get("correct_cases", 0)),
        "full_schema_accuracy_pct": full_schema_accuracy,
        "relationship_aware_accuracy_pct": relationship_aware_accuracy,
        "accuracy_delta_pct": round(relationship_aware_accuracy - full_schema_accuracy, 2),
    }


def _compute_slice_accuracy_deltas(
    full_schema_slices: dict[str, Any],
    relationship_aware_slices: dict[str, Any],
) -> list[dict[str, Any]]:
    deltas: list[dict[str, Any]] = []
    dimensions = sorted(set(full_schema_slices) | set(relationship_aware_slices))
    for dimension in dimensions:
        full_schema_values = full_schema_slices.get(dimension, {})
        relationship_aware_values = relationship_aware_slices.get(dimension, {})
        if not isinstance(full_schema_values, dict) or not isinstance(
            relationship_aware_values, dict
        ):
            continue

        slice_values = sorted(set(full_schema_values) | set(relationship_aware_values))
        for slice_value in slice_values:
            full_schema_stats = full_schema_values.get(slice_value, {})
            relationship_aware_stats = relationship_aware_values.get(slice_value, {})
            if not isinstance(full_schema_stats, dict) or not isinstance(
                relationship_aware_stats, dict
            ):
                continue

            full_schema_accuracy = float(full_schema_stats.get("accuracy_pct", 0.0))
            relationship_aware_accuracy = float(
                relationship_aware_stats.get("accuracy_pct", 0.0)
            )
            deltas.append(
                {
                    "slice_dimension": dimension,
                    "slice_value": slice_value,
                    "full_schema_total": int(full_schema_stats.get("total", 0)),
                    "relationship_aware_total": int(relationship_aware_stats.get("total", 0)),
                    "full_schema_correct": int(full_schema_stats.get("correct", 0)),
                    "relationship_aware_correct": int(
                        relationship_aware_stats.get("correct", 0)
                    ),
                    "full_schema_accuracy_pct": full_schema_accuracy,
                    "relationship_aware_accuracy_pct": relationship_aware_accuracy,
                    "accuracy_delta_pct": round(
                        relationship_aware_accuracy - full_schema_accuracy, 2
                    ),
                }
            )
    return deltas


def _compute_metric_deltas(
    full_schema_metrics: dict[str, Any],
    relationship_aware_metrics: dict[str, Any],
    metric_keys: tuple[str, ...],
) -> list[dict[str, Any]]:
    deltas: list[dict[str, Any]] = []
    for key in metric_keys:
        full_schema_value = float(full_schema_metrics.get(key, 0.0) or 0.0)
        relationship_aware_value = float(relationship_aware_metrics.get(key, 0.0) or 0.0)
        deltas.append(
            {
                "metric": key,
                "full_schema": full_schema_value,
                "relationship_aware": relationship_aware_value,
                "delta": round(relationship_aware_value - full_schema_value, 4),
            }
        )
    return deltas


def _find_slice_delta(
    slice_deltas: list[dict[str, Any]],
    dimension: str,
    value: str,
) -> dict[str, Any] | None:
    for delta in slice_deltas:
        if delta["slice_dimension"] == dimension and delta["slice_value"] == value:
            return delta
    return None


def _relationship_gate_passed(metric_deltas: list[dict[str, Any]]) -> bool:
    metrics_by_name = {str(metric["metric"]): metric for metric in metric_deltas}
    path_coverage_delta = _metric_delta_value(metrics_by_name, "relationship_path_coverage")
    edge_recall_delta = _metric_delta_value(metrics_by_name, "relationship_edge_recall")
    wrong_edge_rate_delta = _metric_delta_value(metrics_by_name, "relationship_wrong_edge_rate")
    return (
        path_coverage_delta > 0
        or edge_recall_delta > 0
        or wrong_edge_rate_delta < 0
    )


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


def _metric_delta_value(metrics_by_name: dict[str, dict[str, Any]], metric_name: str) -> float:
    metric = metrics_by_name.get(metric_name, {})
    return float(metric.get("delta", 0.0) or 0.0)

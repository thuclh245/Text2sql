"""Phase 7D targeted-hardening support: per-slice relationship-reasoning quality.

Phase 7C buckets failures by inspecting the *final generated SQL text*, which
only tells us something real when the generator is a live, reasonably capable
LLM. The join-path/grain plan built by ``SemanticRelationshipReasoner`` is
deterministic and independent of the LLM, so its quality (edge recall, path
coverage, wrong-edge rate) can be measured directly against real gold SQL —
broken down by the same Phase 6B join slices — to find exactly which class of
join structure the reasoner itself handles worst. That is the root-cause
signal Phase 7D hardening should target, and the before/after comparison here
is how "rerun the affected slice" is verified.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from chatsql.analysis.join_slices import JOIN_SLICES, classify_join_relationship_slice
from chatsql.domain.catalog import DatabaseCatalog
from chatsql.domain.gold_case import GoldCase
from chatsql.domain.inference_case import InferenceCase
from chatsql.evaluation.relationship_metrics import aggregate_relationship_metrics

SLICE_ORDER: tuple[str, ...] = (
    "single_table",
    *JOIN_SLICES.keys(),
)
# de-duplicate while preserving order (single_table also appears in JOIN_SLICES)
SLICE_ORDER = tuple(dict.fromkeys(SLICE_ORDER))

_METRIC_KEYS = (
    "edge_recall",
    "edge_precision",
    "wrong_edge_rate",
    "path_coverage",
    "exact_path_accuracy",
    "mean_hop_count",
)


def _load_evaluated_cases(run_dir: Path) -> list[dict[str, Any]]:
    path = run_dir / "evaluated_cases.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found; run `chatsql analysis run` first")
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _bucket_case_metrics(
    records: list[dict[str, Any]],
    catalogs: dict[str, DatabaseCatalog],
) -> dict[str, list[dict[str, Any]]]:
    buckets: dict[str, list[dict[str, Any]]] = {name: [] for name in SLICE_ORDER}
    for rec in records:
        rel = (rec.get("metadata") or {}).get("relationship")
        if not isinstance(rel, dict):
            continue
        catalog = catalogs.get(rec.get("database_id", ""))
        if catalog is None:
            continue
        case = InferenceCase(
            case_id=rec["case_id"],
            question=rec.get("question", ""),
            database_id=rec["database_id"],
        )
        gold = GoldCase(case_id=rec["case_id"], gold_sql=rec.get("gold_sql", ""))
        try:
            slice_name = classify_join_relationship_slice(case, gold, catalog)
        except Exception:
            continue
        buckets[slice_name].append(rel)
    return buckets


def _aggregate_bucket(bucket: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = aggregate_relationship_metrics(bucket)
    return {
        "cases_with_plan": metrics.total_cases,
        "edge_recall": metrics.edge_recall,
        "edge_precision": metrics.edge_precision,
        "wrong_edge_rate": metrics.wrong_edge_rate,
        "path_coverage": metrics.path_coverage,
        "exact_path_accuracy": metrics.exact_path_accuracy,
        "mean_hop_count": metrics.mean_hop_count,
    }


def _quality_score(bucket_metrics: dict[str, Any]) -> float:
    """Single scalar for ranking slices from weakest to strongest reasoner quality.

    Averages edge recall, path coverage, and (1 - wrong_edge_rate) — the three
    metrics where higher is always better — so a slice that is bad on any one
    of them surfaces as a low score without one strong metric masking it.
    """
    return float(
        bucket_metrics["edge_recall"]
        + bucket_metrics["path_coverage"]
        + (1.0 - bucket_metrics["wrong_edge_rate"])
    ) / 3.0


def generate_relationship_slice_metrics_report(
    run_dir: Path,
    catalogs: dict[str, DatabaseCatalog],
    run_name: str = "relationship_aware",
    min_cases_for_bottleneck: int = 5,
) -> dict[str, Any]:
    """Break down relationship-reasoning quality by Phase 6B join slice for one run."""
    records = _load_evaluated_cases(run_dir)
    buckets = _bucket_case_metrics(records, catalogs)

    slices: list[dict[str, Any]] = []
    for name in SLICE_ORDER:
        agg = _aggregate_bucket(buckets[name])
        slices.append({"slice": name, **agg, "quality_score": round(_quality_score(agg), 4)})

    eligible = [s for s in slices if s["cases_with_plan"] >= min_cases_for_bottleneck]
    bottleneck = min(eligible, key=lambda s: s["quality_score"]) if eligible else None

    return {
        "phase": "7D",
        "run_name": run_name,
        "run_dir": str(run_dir),
        "min_cases_for_bottleneck": min_cases_for_bottleneck,
        "slices": slices,
        "bottleneck": {
            "slice": bottleneck["slice"] if bottleneck else None,
            "quality_score": bottleneck["quality_score"] if bottleneck else None,
            "cases_with_plan": bottleneck["cases_with_plan"] if bottleneck else 0,
        },
    }


def format_relationship_slice_metrics_report_md(report: dict[str, Any]) -> str:
    """Render a Phase 7D slice-metrics report as Markdown."""
    lines: list[str] = [
        "# Phase 7D Relationship Slice-Quality Report",
        "",
        f"- **Run:** `{report['run_name']}` ({report['run_dir']})",
        "",
        "## Relationship Quality by Join Slice",
        "| Slice | Cases | Edge Recall | Edge Precision | Wrong-Edge Rate | Path Coverage | "
        "Exact Path | Mean Hops | Quality Score |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for s in report["slices"]:
        lines.append(
            f"| `{s['slice']}` | {s['cases_with_plan']} | {s['edge_recall']:.4f} | "
            f"{s['edge_precision']:.4f} | {s['wrong_edge_rate']:.4f} | "
            f"{s['path_coverage']:.4f} | {s['exact_path_accuracy']:.4f} | "
            f"{s['mean_hop_count']:.2f} | {s['quality_score']:.4f} |"
        )

    bottleneck = report["bottleneck"]
    lines.extend(["", "## Bottleneck"])
    if bottleneck["slice"] is None:
        lines.append(
            "- No slice had enough cases with a relationship plan to identify a bottleneck."
        )
    else:
        lines.append(
            f"- **Weakest slice:** `{bottleneck['slice']}` "
            f"(quality score {bottleneck['quality_score']:.4f}, "
            f"{bottleneck['cases_with_plan']} cases)."
        )
        lines.append(
            "- Phase 7D hardening should target this slice, then rerun and compare "
            "with `phase7d-hardening-gate`."
        )

    return "\n".join(lines) + "\n"


def save_relationship_slice_metrics_report(report: dict[str, Any], output_dir: Path) -> None:
    """Save Phase 7D slice-metrics report as JSON and Markdown."""
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "relationship_slice_metrics_report.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    (output_dir / "relationship_slice_metrics_report.md").write_text(
        format_relationship_slice_metrics_report_md(report),
        encoding="utf-8",
    )


def generate_relationship_hardening_gate_report(
    before_run_dir: Path,
    after_run_dir: Path,
    catalogs: dict[str, DatabaseCatalog],
    target_slice: str,
    before_name: str = "before_hardening",
    after_name: str = "after_hardening",
    regression_tolerance: float = 0.01,
) -> dict[str, Any]:
    """Compare relationship-reasoning quality before/after a Phase 7D fix.

    Passes when the targeted slice's quality score improves and no other
    slice regresses by more than ``regression_tolerance``.
    """
    if target_slice not in SLICE_ORDER:
        raise ValueError(f"Unknown slice {target_slice!r}; expected one of {SLICE_ORDER}")

    before_records = _load_evaluated_cases(before_run_dir)
    after_records = _load_evaluated_cases(after_run_dir)
    before_buckets = _bucket_case_metrics(before_records, catalogs)
    after_buckets = _bucket_case_metrics(after_records, catalogs)

    slice_deltas: list[dict[str, Any]] = []
    for name in SLICE_ORDER:
        before_agg = _aggregate_bucket(before_buckets[name])
        after_agg = _aggregate_bucket(after_buckets[name])
        before_score = _quality_score(before_agg)
        after_score = _quality_score(after_agg)
        slice_deltas.append(
            {
                "slice": name,
                "before_cases": before_agg["cases_with_plan"],
                "after_cases": after_agg["cases_with_plan"],
                "before_quality_score": round(before_score, 4),
                "after_quality_score": round(after_score, 4),
                "quality_score_delta": round(after_score - before_score, 4),
                "before": before_agg,
                "after": after_agg,
            }
        )

    target = next(d for d in slice_deltas if d["slice"] == target_slice)
    target_improved = (
        target["before_cases"] > 0
        and target["after_cases"] > 0
        and target["quality_score_delta"] > 0
    )
    no_other_regression = all(
        d["quality_score_delta"] >= -regression_tolerance
        for d in slice_deltas
        if d["slice"] != target_slice and d["before_cases"] > 0 and d["after_cases"] > 0
    )

    return {
        "phase": "7D",
        "before_name": before_name,
        "after_name": after_name,
        "before_run_dir": str(before_run_dir),
        "after_run_dir": str(after_run_dir),
        "target_slice": target_slice,
        "regression_tolerance": regression_tolerance,
        "slice_deltas": slice_deltas,
        "gate": {
            "target_slice_improved": target_improved,
            "no_other_slice_regressed": no_other_regression,
            "passed": target_improved and no_other_regression,
        },
    }


def format_relationship_hardening_gate_report_md(report: dict[str, Any]) -> str:
    """Render a Phase 7D hardening gate report as Markdown."""
    gate = report["gate"]
    status = "PASS" if gate["passed"] else "FAIL"

    lines: list[str] = [
        "# Phase 7D Targeted Hardening Gate Report",
        "",
        f"- **Before:** `{report['before_name']}` ({report['before_run_dir']})",
        f"- **After:** `{report['after_name']}` ({report['after_run_dir']})",
        f"- **Target slice:** `{report['target_slice']}`",
        f"- **Gate Status:** **{status}**",
        "",
        "## Gate Criteria",
        "| Criterion | Passed |",
        "|---|:---:|",
        f"| Target slice quality improved | {_yes_no(gate['target_slice_improved'])} |",
        f"| No other slice regressed > {report['regression_tolerance']:.2%} | "
        f"{_yes_no(gate['no_other_slice_regressed'])} |",
        "",
        "## Relationship Quality by Slice (Before -> After)",
        "| Slice | Cases (before/after) | Quality Before | Quality After | Delta |",
        "|---|---:|---:|---:|---:|",
    ]
    for d in report["slice_deltas"]:
        marker = " **<- target**" if d["slice"] == report["target_slice"] else ""
        lines.append(
            f"| `{d['slice']}`{marker} | {d['before_cases']} / {d['after_cases']} | "
            f"{d['before_quality_score']:.4f} | {d['after_quality_score']:.4f} | "
            f"{d['quality_score_delta']:+.4f} |"
        )

    return "\n".join(lines) + "\n"


def save_relationship_hardening_gate_report(report: dict[str, Any], output_dir: Path) -> None:
    """Save Phase 7D hardening gate report as JSON and Markdown."""
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "relationship_hardening_gate_report.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    (output_dir / "relationship_hardening_gate_report.md").write_text(
        format_relationship_hardening_gate_report_md(report),
        encoding="utf-8",
    )


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"

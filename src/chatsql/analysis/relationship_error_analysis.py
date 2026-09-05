"""Phase 7C error analysis: bucket relationship-aware run failures by root cause.

Groups every incorrect case from a run into one of five root-cause buckets
(missing table, wrong FK, missing bridge, fanout/grain, SQL generation
despite a correct plan) so Phase 7D can target the single largest bottleneck
instead of refactoring broadly.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from chatsql.analysis.join_slices import is_bridge_table_required_slice
from chatsql.analysis.reports import analyze_run_directory, load_labeled_cases
from chatsql.analysis.taxonomy import LabeledCase
from chatsql.domain.catalog import DatabaseCatalog
from chatsql.domain.gold_case import GoldCase
from chatsql.domain.inference_case import InferenceCase

ERROR_BUCKETS: tuple[str, ...] = (
    "missing_table",
    "wrong_fk",
    "missing_bridge",
    "fanout_grain",
    "sql_generation_despite_correct_plan",
)

BUCKET_LABELS: dict[str, str] = {
    "missing_table": "Missing table",
    "wrong_fk": "Wrong FK / join path",
    "missing_bridge": "Missing bridge table",
    "fanout_grain": "Fanout / grain error",
    "sql_generation_despite_correct_plan": "SQL generation despite correct plan",
}

_MISSING_TABLE_CODES = ("E01",)
_JOIN_PATH_CODES = ("E10", "E12")
_GRAIN_CODES = ("E13",)
_BRIDGE_ELIGIBLE_CODES = _MISSING_TABLE_CODES + _JOIN_PATH_CODES + _GRAIN_CODES


def classify_relationship_error(case: LabeledCase, bridge_required: bool) -> str:
    """Assign one Phase 7C bucket to a single incorrect labeled case.

    ``bridge_required`` takes priority over the raw error code: a case whose
    gold query needs an unlinked intermediate table is a bridge-expansion
    failure regardless of whether the diagnostic tree happened to label it
    E01/E10/E12/E13, so it must not be double counted under those buckets.
    """
    primary = case.primary_error
    if bridge_required and primary in _BRIDGE_ELIGIBLE_CODES:
        return "missing_bridge"
    if primary in _MISSING_TABLE_CODES:
        return "missing_table"
    if primary in _JOIN_PATH_CODES:
        return "wrong_fk"
    if primary in _GRAIN_CODES or "E13" in case.secondary_errors:
        return "fanout_grain"
    return "sql_generation_despite_correct_plan"


def _is_bridge_required(
    case: LabeledCase,
    catalogs: dict[str, DatabaseCatalog] | None,
) -> bool:
    if not catalogs:
        return False
    catalog = catalogs.get(case.database_id)
    if catalog is None:
        return False
    inference_case = InferenceCase(
        case_id=case.case_id,
        question=case.question,
        database_id=case.database_id,
    )
    gold = GoldCase(case_id=case.case_id, gold_sql=case.gold_sql)
    try:
        return is_bridge_table_required_slice(inference_case, gold, catalog)
    except Exception:
        return False


def _load_or_generate_labeled_cases(run_dir: Path) -> list[LabeledCase]:
    labeled_path = run_dir / "error_analysis" / "labeled_cases.jsonl"
    if not labeled_path.exists():
        analyze_run_directory(run_dir)
    return load_labeled_cases(labeled_path)


def generate_relationship_error_analysis_report(
    run_dir: Path,
    catalogs: dict[str, DatabaseCatalog] | None = None,
    run_name: str = "relationship_aware",
    example_limit: int = 5,
) -> dict[str, Any]:
    """Bucket every incorrect case in ``run_dir`` into a Phase 7C root-cause bucket.

    ``catalogs`` (keyed by database_id) enables accurate missing-bridge
    detection via the relationship graph; without it, bridge-required cases
    fall back into whichever bucket their raw error code implies, and the
    report flags ``bridge_detection_available: false`` so that caveat is
    visible to a reader deciding where to look next.
    """
    labeled_cases = _load_or_generate_labeled_cases(run_dir)
    incorrect_cases = [c for c in labeled_cases if not c.execution_correct]
    total_incorrect = len(incorrect_cases)

    bucket_counts: Counter[str] = Counter()
    bucket_examples: dict[str, list[str]] = {bucket: [] for bucket in ERROR_BUCKETS}
    bucket_error_codes: dict[str, Counter[str]] = {bucket: Counter() for bucket in ERROR_BUCKETS}

    for case in incorrect_cases:
        bridge_required = _is_bridge_required(case, catalogs)
        bucket = classify_relationship_error(case, bridge_required)
        bucket_counts[bucket] += 1
        bucket_error_codes[bucket][case.primary_error] += 1
        if len(bucket_examples[bucket]) < example_limit:
            bucket_examples[bucket].append(case.case_id)

    buckets: list[dict[str, Any]] = []
    for bucket in ERROR_BUCKETS:
        count = bucket_counts.get(bucket, 0)
        pct = round((count / total_incorrect * 100.0), 2) if total_incorrect else 0.0
        buckets.append(
            {
                "bucket": bucket,
                "label": BUCKET_LABELS[bucket],
                "count": count,
                "pct_of_incorrect": pct,
                "example_case_ids": bucket_examples[bucket],
                "error_code_breakdown": dict(bucket_error_codes[bucket]),
            }
        )
    buckets.sort(key=lambda b: (b["count"], b["bucket"]), reverse=True)

    bottleneck = buckets[0] if buckets and buckets[0]["count"] > 0 else None

    return {
        "phase": "7C",
        "run_name": run_name,
        "run_dir": str(run_dir),
        "total_cases": len(labeled_cases),
        "correct_cases": len(labeled_cases) - total_incorrect,
        "total_incorrect": total_incorrect,
        "bridge_detection_available": bool(catalogs),
        "buckets": buckets,
        "bottleneck": {
            "bucket": bottleneck["bucket"] if bottleneck else None,
            "label": bottleneck["label"] if bottleneck else None,
            "count": bottleneck["count"] if bottleneck else 0,
            "pct_of_incorrect": bottleneck["pct_of_incorrect"] if bottleneck else 0.0,
        },
    }


def format_relationship_error_analysis_report_md(report: dict[str, Any]) -> str:
    """Render a Phase 7C error analysis report as Markdown."""
    bridge_note = (
        "enabled (catalogs loaded)"
        if report["bridge_detection_available"]
        else "unavailable — no catalogs provided; bridge-required cases are "
        "folded into missing_table/wrong_fk/fanout_grain instead"
    )

    lines: list[str] = [
        "# Phase 7C Error Analysis Report",
        "",
        f"- **Run:** `{report['run_name']}` ({report['run_dir']})",
        f"- **Total cases:** {report['total_cases']} "
        f"(correct: {report['correct_cases']}, incorrect: {report['total_incorrect']})",
        f"- **Bridge detection:** {bridge_note}",
        "",
        "## Error Buckets",
        "| Bucket | Count | % of Incorrect | Error Codes | Example Cases |",
        "|---|---:|---:|---|---|",
    ]

    for bucket in report["buckets"]:
        codes = (
            ", ".join(f"{code}×{count}" for code, count in bucket["error_code_breakdown"].items())
            or "-"
        )
        examples = ", ".join(bucket["example_case_ids"]) or "-"
        lines.append(
            f"| {bucket['label']} | {bucket['count']} | {bucket['pct_of_incorrect']:.2f}% | "
            f"{codes} | {examples} |"
        )

    bottleneck = report["bottleneck"]
    lines.extend(["", "## Bottleneck"])
    if bottleneck["bucket"] is None:
        lines.append("- No incorrect cases found; nothing to prioritize.")
    else:
        lines.append(
            f"- **Primary bottleneck:** {bottleneck['label']} "
            f"({bottleneck['count']} cases, "
            f"{bottleneck['pct_of_incorrect']:.2f}% of incorrect cases)."
        )
        lines.append(
            "- Phase 7D should fix this bucket first, then rerun only the slice it affects."
        )

    return "\n".join(lines) + "\n"


def save_relationship_error_analysis_report(
    report: dict[str, Any],
    output_dir: Path,
) -> None:
    """Save Phase 7C error analysis report as JSON and Markdown."""
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "relationship_error_analysis_report.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    (output_dir / "relationship_error_analysis_report.md").write_text(
        format_relationship_error_analysis_report_md(report),
        encoding="utf-8",
    )

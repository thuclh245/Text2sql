"""Error comparison utility across experiment runs (P5 compare.py)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from chatsql.analysis.reports import generate_error_summary_json
from chatsql.analysis.taxonomy import LabeledCase


def compare_error_runs(
    run_a_labels: list[LabeledCase],
    run_b_labels: list[LabeledCase],
    name_a: str = "Baseline (Run A)",
    name_b: str = "Candidate (Run B)",
) -> dict[str, Any]:
    """Compare error distribution and accuracy between two experiment runs."""
    sum_a = generate_error_summary_json(run_a_labels)
    sum_b = generate_error_summary_json(run_b_labels)

    acc_a = sum_a["accuracy_pct"]
    acc_b = sum_b["accuracy_pct"]
    acc_diff = round(acc_b - acc_a, 2)

    # Category shift
    all_categories = sorted(
        set(sum_a["error_budget_pct"].keys()) | set(sum_b["error_budget_pct"].keys())
    )
    category_shifts: list[dict[str, Any]] = []

    for cat in all_categories:
        pct_a = sum_a["error_budget_pct"].get(cat, 0.0)
        pct_b = sum_b["error_budget_pct"].get(cat, 0.0)
        diff = round(pct_b - pct_a, 2)
        category_shifts.append(
            {
                "category": cat,
                "pct_a": pct_a,
                "pct_b": pct_b,
                "diff_pct": diff,
            }
        )

    return {
        "name_a": name_a,
        "name_b": name_b,
        "accuracy_a": acc_a,
        "accuracy_b": acc_b,
        "accuracy_diff": acc_diff,
        "summary_a": sum_a,
        "summary_b": sum_b,
        "category_shifts": category_shifts,
    }


def format_error_comparison_md(comparison: dict[str, Any]) -> str:
    """Format comparison result into Markdown table."""
    name_a = comparison["name_a"]
    name_b = comparison["name_b"]
    acc_a = comparison["accuracy_a"]
    acc_b = comparison["accuracy_b"]
    diff = comparison["accuracy_diff"]

    lines: list[str] = []
    lines.append(f"# Error Comparison: {name_a} vs {name_b}")
    lines.append("")
    lines.append("## Overall Accuracy")
    lines.append(f"- **{name_a}:** {acc_a:.2f}% EX")
    lines.append(f"- **{name_b}:** {acc_b:.2f}% EX")
    lines.append(f"- **Delta:** `{'+' if diff >= 0 else ''}{diff:.2f}%`")
    lines.append("")

    lines.append("## Error Budget Category Shift")
    lines.append(f"| Error Category | {name_a} (%) | {name_b} (%) | Shift (%) |")
    lines.append("|---|:---:|:---:|:---:|")

    for shift in comparison["category_shifts"]:
        d = shift["diff_pct"]
        sign = "+" if d > 0 else ""
        row = (
            f"| {shift['category']} | {shift['pct_a']:.2f}% | "
            f"{shift['pct_b']:.2f}% | `{sign}{d:.2f}%` |"
        )
        lines.append(row)

    lines.append("")
    return "\n".join(lines)


def compare_run_directories(
    run_dir_a: Path,
    run_dir_b: Path,
    name_a: str | None = None,
    name_b: str | None = None,
) -> dict[str, Any]:
    """Compare error analysis outcomes between two experiment run directories."""
    from chatsql.analysis.reports import analyze_run_directory

    sum_a_path = run_dir_a / "error_analysis" / "summary.json"
    if sum_a_path.exists():
        with sum_a_path.open("r", encoding="utf-8") as f:
            sum_a = json.load(f)
    else:
        sum_a = analyze_run_directory(run_dir_a)

    sum_b_path = run_dir_b / "error_analysis" / "summary.json"
    if sum_b_path.exists():
        with sum_b_path.open("r", encoding="utf-8") as f:
            sum_b = json.load(f)
    else:
        sum_b = analyze_run_directory(run_dir_b)

    label_a = name_a or run_dir_a.name
    label_b = name_b or run_dir_b.name

    acc_a = sum_a["accuracy_pct"]
    acc_b = sum_b["accuracy_pct"]
    acc_diff = round(acc_b - acc_a, 2)

    all_categories = sorted(
        set(sum_a.get("error_budget_pct", {}).keys())
        | set(sum_b.get("error_budget_pct", {}).keys())
    )
    category_shifts: list[dict[str, Any]] = []
    for cat in all_categories:
        pct_a = sum_a.get("error_budget_pct", {}).get(cat, 0.0)
        pct_b = sum_b.get("error_budget_pct", {}).get(cat, 0.0)
        diff = round(pct_b - pct_a, 2)
        category_shifts.append(
            {
                "category": cat,
                "pct_a": pct_a,
                "pct_b": pct_b,
                "diff_pct": diff,
            }
        )

    return {
        "name_a": label_a,
        "name_b": label_b,
        "accuracy_a": acc_a,
        "accuracy_b": acc_b,
        "accuracy_diff": acc_diff,
        "summary_a": sum_a,
        "summary_b": sum_b,
        "category_shifts": category_shifts,
    }

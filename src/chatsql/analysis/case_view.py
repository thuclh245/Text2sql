"""Case rendering view for manual review workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from chatsql.analysis.taxonomy import TAXONOMY_MAP, LabeledCase


def render_case_for_review(
    labeled_case: LabeledCase,
    retrieved_tables: tuple[str, ...] | None = None,
    retrieved_columns: tuple[str, ...] | None = None,
    execution_info: dict[str, Any] | None = None,
) -> str:
    """Render a single case in human-readable plain text / Markdown format for review."""
    if labeled_case.primary_error == "NONE" or labeled_case.execution_correct:
        cat_name = "Correct Execution"
        err_name = "No Error"
    else:
        info = TAXONOMY_MAP.get(labeled_case.primary_error)
        cat_name = info.category.value if info else "Unknown"
        err_name = info.name if info else labeled_case.primary_error

    lines: list[str] = []
    lines.append("=" * 80)
    lines.append(f"CASE ID: {labeled_case.case_id}  |  DATABASE: {labeled_case.database_id}")
    lines.append(
        f"STATUS:  {'CORRECT (PASS)' if labeled_case.execution_correct else 'INCORRECT (FAIL)'}"
    )
    lines.append(f"PRE-LABEL: [{labeled_case.primary_error}] {err_name} ({cat_name})")
    if labeled_case.secondary_errors:
        lines.append(f"SECONDARY ERRORS: {', '.join(labeled_case.secondary_errors)}")
    lines.append("-" * 80)
    lines.append("QUESTION:")
    lines.append(f"  {labeled_case.question}")
    lines.append("-" * 80)

    if retrieved_tables is not None:
        lines.append("GROUNDED / RETRIEVED SCHEMA:")
        lines.append(f"  Tables: {', '.join(retrieved_tables) if retrieved_tables else '(none)'}")
        if retrieved_columns:
            lines.append(
                f"  Columns: {', '.join(retrieved_columns[:20])}"
                + ("..." if len(retrieved_columns) > 20 else "")
            )
        lines.append("-" * 80)

    lines.append("PREDICTED SQL:")
    lines.append(f"  {labeled_case.predicted_sql}")
    lines.append("-" * 80)
    lines.append("GOLD SQL (Reviewer Only):")
    lines.append(f"  {labeled_case.gold_sql}")
    lines.append("-" * 80)

    if execution_info:
        lines.append("EXECUTION TRACE:")
        lines.append(f"  Executed: {execution_info.get('executed', False)}")
        if execution_info.get("error"):
            lines.append(f"  Error:    {execution_info['error']}")
        if "row_count" in execution_info:
            lines.append(f"  Rows:     {execution_info['row_count']}")
        lines.append("-" * 80)

    if labeled_case.metadata:
        lines.append("DIAGNOSTIC METADATA:")
        for k, v in labeled_case.metadata.items():
            lines.append(f"  {k}: {v}")
        lines.append("-" * 80)

    if labeled_case.reviewer_notes:
        lines.append(f"MANUAL REVIEWER NOTES: {labeled_case.reviewer_notes}")
        lines.append("-" * 80)

    lines.append("=" * 80)
    return "\n".join(lines)


def export_cases_for_review(
    labeled_cases: list[LabeledCase],
    output_path: Path,
    limit: int | None = None,
    case_context: dict[str, dict[str, Any]] | None = None,
) -> None:
    """Export formatted case reviews to a Markdown audit file.

    ``case_context`` maps case_id to an optional dict with keys
    "retrieved_tables", "retrieved_columns", and "execution_info", used to
    render the grounded schema and execution trace alongside each case.
    """
    selected = labeled_cases[:limit] if limit is not None else labeled_cases
    blocks: list[str] = [
        "# CHATSQL — Manual Audit Review Sheet",
        f"Total cases rendered: {len(selected)}",
        "",
    ]
    for case in selected:
        ctx = (case_context or {}).get(case.case_id, {})
        rendered = render_case_for_review(
            case,
            retrieved_tables=ctx.get("retrieved_tables"),
            retrieved_columns=ctx.get("retrieved_columns"),
            execution_info=ctx.get("execution_info"),
        )
        blocks.append(f"```text\n{rendered}\n```\n")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(blocks), encoding="utf-8")

"""Slicing logic for error analysis (P5-T03)."""

from __future__ import annotations

import re
from typing import Any

from chatsql.analysis.taxonomy import LabeledCase


def compute_join_depth(sql: str) -> int:
    """Compute number of JOIN clauses in SQL query."""
    return len(re.findall(r"\bJOIN\b", sql, re.IGNORECASE))


def slice_case(
    labeled_case: LabeledCase,
    table_count_in_catalog: int | None = None,
    retrieved_table_count: int | None = None,
    gold_table_count: int | None = None,
    difficulty: str | None = None,
) -> dict[str, Any]:
    """Categorize a single labeled case into multi-dimensional slices."""
    gold_sql = labeled_case.gold_sql
    joins = compute_join_depth(gold_sql)

    # 1. Single vs Multi-table slice
    is_multi_table = joins > 0 or (gold_table_count is not None and gold_table_count > 1)
    table_slice = "multi_table" if is_multi_table else "single_table"

    # 2. Join depth slice
    if joins == 0:
        join_depth_slice = "0_joins"
    elif joins == 1:
        join_depth_slice = "1_join"
    else:
        join_depth_slice = "2+_joins"

    # 3. Schema size slice
    if table_count_in_catalog is None:
        schema_size_slice = "unknown"
    elif table_count_in_catalog <= 5:
        schema_size_slice = "small (<=5 tables)"
    elif table_count_in_catalog <= 15:
        schema_size_slice = "medium (6-15 tables)"
    else:
        schema_size_slice = "large (>15 tables)"

    # 4. Difficulty slice
    diff_slice = (
        difficulty if difficulty else labeled_case.metadata.get("difficulty", "unspecified")
    )

    # 5. High noise retrieval slice
    high_noise = False
    if retrieved_table_count is not None and gold_table_count is not None and gold_table_count > 0:
        high_noise = retrieved_table_count > (2 * gold_table_count)

    # 6. Execution failure slice
    is_exec_failure = labeled_case.primary_error in ("E41", "E42", "E91")

    return {
        "case_id": labeled_case.case_id,
        "table_slice": table_slice,
        "join_depth": join_depth_slice,
        "schema_size": schema_size_slice,
        "difficulty": diff_slice,
        "high_noise_retrieval": high_noise,
        "execution_failure": is_exec_failure,
    }


def aggregate_slice_performance(
    labeled_cases: list[LabeledCase],
    slice_data: list[dict[str, Any]],
) -> dict[str, Any]:
    """Aggregate accuracy and error breakdown by slice."""
    by_case_id = {c.case_id: c for c in labeled_cases}

    slices: dict[str, dict[str, dict[str, Any]]] = {
        "table_slice": {},
        "join_depth": {},
        "schema_size": {},
        "difficulty": {},
        "high_noise_retrieval": {},
        "execution_failure": {},
    }

    for item in slice_data:
        case_id = item["case_id"]
        labeled = by_case_id.get(case_id)
        if not labeled:
            continue

        is_correct = labeled.execution_correct

        for slice_dim in slices:
            val = str(item.get(slice_dim))
            if val not in slices[slice_dim]:
                slices[slice_dim][val] = {"total": 0, "correct": 0, "errors": 0}

            slices[slice_dim][val]["total"] += 1
            if is_correct:
                slices[slice_dim][val]["correct"] += 1
            else:
                slices[slice_dim][val]["errors"] += 1

    # Compute accuracy percentages
    results: dict[str, Any] = {}
    for slice_dim, slice_values in slices.items():
        results[slice_dim] = {}
        for val, counts in slice_values.items():
            tot = counts["total"]
            corr = counts["correct"]
            acc = (corr / tot * 100.0) if tot > 0 else 0.0
            results[slice_dim][val] = {
                "total": tot,
                "correct": corr,
                "errors": counts["errors"],
                "accuracy_pct": round(acc, 2),
            }

    return results

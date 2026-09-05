"""Error budget calculations, summary reports, and research decision gate."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from chatsql.analysis.taxonomy import TAXONOMY_MAP, ErrorCategory, LabeledCase


def recommend_next_research_track(error_budget_pct: dict[str, float]) -> dict[str, Any]:
    """Apply scientific decision rules to determine the next research track.

    Decision rules:
    - If Retrieval / Grounding dominates, focus on grounding retrieval research.
    - If Relationship / Join dominates, focus on join relationship research.
    - If Business / Semantic dominates, focus on semantic model research.
    - If SQL Generation dominates -> Prompt / LLM Reasoning strategy refinement
    """
    # Exclude NONE (Correct) when finding bottleneck
    error_cats = {k: v for k, v in error_budget_pct.items() if k != ErrorCategory.NONE.value}
    if not error_cats or sum(error_cats.values()) == 0:
        return {
            "recommended_track": "grounding_retrieval_research",
            "reason": "Zero errors detected; default to grounding retrieval research.",
        }

    dominant_cat = max(error_cats, key=error_cats.get)  # type: ignore[arg-type]
    dominant_pct = error_cats[dominant_cat]

    if dominant_cat == ErrorCategory.RETRIEVAL_GROUNDING.value:
        recommended = "grounding_retrieval_research"
        track_name = "Grounding and Retrieval Research"
        reason = (
            f"Retrieval/Grounding dominates the error budget ({dominant_pct:.1f}% of errors). "
            "Focus must be on schema grounding, dense table/column retrieval, and noise reduction."
        )
    elif dominant_cat == ErrorCategory.RELATIONSHIP_JOIN.value:
        recommended = "join_relationship_research"
        track_name = "Join and Relationship Research"
        reason = (
            f"Relationship/Join errors dominate the error budget ({dominant_pct:.1f}% of errors). "
            "Focus must be on join path resolution, relationship graphs, and "
            "grain/cardinality analysis."
        )
    elif dominant_cat == ErrorCategory.BUSINESS_SEMANTIC.value:
        recommended = "semantic_model_research"
        track_name = "Semantic Model Research"
        reason = (
            f"Business/Semantic errors dominate the error budget ({dominant_pct:.1f}% of errors). "
            "Prioritize semantic grounding and test Oracle Semantic Model IR."
        )
    else:
        recommended = "llm_reasoning_refinement"
        track_name = f"LLM Reasoning Refinement (Dominant category: {dominant_cat})"
        reason = (
            f"Errors are dominated by {dominant_cat} ({dominant_pct:.1f}%). "
            "LLM generation/prompting or value grounding requires refinement."
        )

    return {
        "recommended_track": recommended,
        "recommended_track_name": track_name,
        "dominant_category": dominant_cat,
        "dominant_percentage": round(dominant_pct, 2),
        "reason": reason,
    }


def generate_error_summary_json(
    labeled_cases: list[LabeledCase],
    slice_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate structured summary JSON dictionary including Error Budget and Research Decision."""
    total_cases = len(labeled_cases)
    correct_count = sum(1 for c in labeled_cases if c.execution_correct)
    incorrect_count = total_cases - correct_count
    accuracy_pct = (correct_count / total_cases * 100.0) if total_cases > 0 else 0.0

    # Error code breakdown
    code_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()

    for case in labeled_cases:
        code_counts[case.primary_error] += 1
        category_counts[case.primary_category.value] += 1

    # Calculate Error Budget percentage (relative to total incorrect cases)
    error_budget_pct: dict[str, float] = {}
    for cat, count in category_counts.items():
        if cat == ErrorCategory.NONE.value:
            continue
        pct = (count / incorrect_count * 100.0) if incorrect_count > 0 else 0.0
        error_budget_pct[cat] = round(pct, 2)

    decision = recommend_next_research_track(error_budget_pct)

    code_breakdown: list[dict[str, Any]] = []
    for code, count in code_counts.most_common():
        if code == "NONE":
            continue
        info = TAXONOMY_MAP.get(code)
        code_breakdown.append(
            {
                "code": code,
                "name": info.name if info else code,
                "category": info.category.value if info else "Unknown",
                "count": count,
                "pct_of_errors": round((count / incorrect_count * 100.0), 2)
                if incorrect_count > 0
                else 0.0,
            }
        )

    return {
        "total_cases": total_cases,
        "correct_cases": correct_count,
        "incorrect_cases": incorrect_count,
        "accuracy_pct": round(accuracy_pct, 2),
        "error_budget_pct": error_budget_pct,
        "category_counts": dict(category_counts),
        "error_code_breakdown": code_breakdown,
        "slices": slice_summary or {},
        "decision": decision,
    }


def generate_error_summary_md(summary: dict[str, Any]) -> str:
    """Generate human-readable Markdown summary report for gate review."""
    total = summary["total_cases"]
    correct = summary["correct_cases"]
    incorrect = summary["incorrect_cases"]
    acc = summary["accuracy_pct"]
    decision = summary["decision"]

    lines: list[str] = []
    lines.append("# CHATSQL Error Analysis Report")
    lines.append("")
    lines.append("## 1. Overall Performance Overview")
    lines.append(f"- **Total Benchmark Cases:** {total}")
    lines.append(f"- **Execution Correct (EX):** {correct} ({acc:.2f}%)")
    lines.append(f"- **Total Incorrect Cases:** {incorrect}")
    lines.append("")

    lines.append("## 2. Error Budget Breakdown")
    lines.append("| Category | Incorrect Cases | Error Budget Share (%) |")
    lines.append("|---|:---:|:---:|")

    for cat, pct in summary["error_budget_pct"].items():
        cnt = summary["category_counts"].get(cat, 0)
        lines.append(f"| {cat} | {cnt} | **{pct:.2f}%** |")
    lines.append("")

    lines.append("## 3. Specific Error Code Breakdown")
    lines.append("| Code | Error Name | Category | Count | % of Errors |")
    lines.append("|---|---|---|:---:|:---:|")
    for item in summary["error_code_breakdown"]:
        row = (
            f"| `{item['code']}` | {item['name']} | {item['category']} | "
            f"{item['count']} | {item['pct_of_errors']:.1f}% |"
        )
        lines.append(row)
    lines.append("")

    if summary.get("slices"):
        lines.append("## 4. Slice Performance Analysis")
        for slice_dim, slice_vals in summary["slices"].items():
            lines.append(f"### Slice Dimension: `{slice_dim}`")
            lines.append("| Sub-Slice | Total | Correct | Errors | Accuracy (%) |")
            lines.append("|---|:---:|:---:|:---:|:---:|")
            for sub_name, metrics in slice_vals.items():
                row = (
                    f"| {sub_name} | {metrics['total']} | {metrics['correct']} | "
                    f"{metrics['errors']} | {metrics['accuracy_pct']:.2f}% |"
                )
                lines.append(row)
            lines.append("")

    lines.append("## 5. Scientific Gate & Research Recommendation")
    lines.append(f"- **Observed Bottleneck:** {decision.get('dominant_category', 'N/A')}")
    lines.append(
        f"- **Recommended Research Track:** "
        f"`{decision.get('recommended_track', 'grounding_retrieval_research')}`"
    )
    lines.append(f"- **Research Track Title:** {decision.get('recommended_track_name', '')}")
    lines.append(f"- **Scientific Rationale:** {decision['reason']}")
    lines.append("")

    return "\n".join(lines)


def generate_decision_memo(
    summary: dict[str, Any],
    baseline_name: str = "B0 Full-Schema Control",
) -> str:
    """Generate the mandatory 7-field research decision memo."""
    decision = summary["decision"]
    bottleneck = decision.get("dominant_category", "Retrieval / Grounding")
    rec_track = decision.get("recommended_track", "grounding_retrieval_research")
    total = summary.get("total_cases", 0)
    correct = summary.get("correct_cases", 0)
    incorrect = summary.get("incorrect_cases", 0)
    acc = summary.get("accuracy_pct", 0.0)

    # Find affected slices (slices with lowest accuracy)
    affected_slices_lines: list[str] = []
    slices = summary.get("slices", {})
    for dim_name, vals in slices.items():
        if isinstance(vals, dict):
            for val_name, stats in vals.items():
                if (
                    isinstance(stats, dict)
                    and stats.get("total", 0) > 0
                    and stats.get("accuracy_pct", 100.0) < acc
                ):
                    pct_val = stats["accuracy_pct"]
                    affected_slices_lines.append(
                        f"- `{dim_name}={val_name}`: {pct_val:.1f}% EX "
                        f"({stats['correct']}/{stats['total']})"
                    )

    affected_slices_str = (
        "\n".join(affected_slices_lines)
        if affected_slices_lines
        else "- multi_table and large schema slices"
    )

    if rec_track == "grounding_retrieval_research":
        hypotheses = (
            "- H1 (Dense Grounding): Bi-encoder dense column/table retrieval outperforms "
            "BM25 lexical retrieval on large-schema databases.\n"
            "- H2 (Bridge Closure): Foreign-key closure expansion prevents missing join tables "
            "(E01) without excessive noise."
        )
        why_research = (
            "Grounding under token budgets in multi-table databases involves a Pareto trade-off "
            "between recall (avoiding E01/E02) and prompt context noise (E03/E04). Simple "
            "heuristics fail when column names are ambiguous without semantic embeddings."
        )
    elif rec_track == "join_relationship_research":
        hypotheses = (
            "- H1 (Relationship Plan): Explicit join path graph search prevents incorrect "
            "foreign key joins (E10/E12) in deep schemas.\n"
            "- H2 (Grain Inference): Cardinality inference prevents fanout errors (E13) "
            "during aggregations."
        )
        why_research = (
            "Join path resolution on multi-hop relationships is an NP-hard Steiner tree problem "
            "over foreign-key graphs with multiple candidate paths between identical endpoints."
        )
    elif rec_track == "semantic_model_research":
        hypotheses = (
            "- H1 (Semantic Model IR): Semantic layer abstractions (metrics, dimensions) "
            "eliminate business concept confusion (E20) and measure miscalculations (E21)."
        )
        why_research = (
            "Translating natural language business questions into SQL measures requires "
            "formal semantic models rather than prompt engineering alone."
        )
    else:
        hypotheses = (
            "- H1 (Few-shot Prompting): Domain-specific few-shot exemplars reduce pure "
            "SQL generation logical errors (E40)."
        )
        why_research = (
            "SQL synthesis errors stem from complex nested subquery reasoning and dialect nuances."
        )

    dom_pct = decision.get("dominant_percentage", 0.0)
    err_budget_str = json.dumps(summary.get("error_budget_pct", {}), indent=2)
    evidence_text = (
        f"Across {total} benchmark cases, CHATSQL baseline achieved {acc:.2f}% Execution "
        f"Accuracy ({correct} correct, {incorrect} incorrect). Analysis reveals {dom_pct}% "
        f"of failures are attributed to {bottleneck}. Error budget breakdown:\n{err_budget_str}"
    )
    memo = f"""# CHATSQL Scientific Exit Gate Memo

Observed bottleneck:
{bottleneck} ({dom_pct}% of error budget)

Evidence:
{evidence_text}

Affected slices:
{affected_slices_str}

Baseline:
{baseline_name}

Hypothesis candidates:
{hypotheses}

Why this is not only engineering:
{why_research}

Next research track:
{rec_track} ({decision.get("recommended_track_name", "")})
"""
    return memo


def save_error_analysis_artifacts(
    output_dir: Path,
    labeled_cases: list[LabeledCase],
    summary: dict[str, Any],
) -> None:
    """Save all error-analysis deliverables to the specified directory."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Save labeled_cases.jsonl
    jsonl_path = output_dir / "labeled_cases.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        for case in labeled_cases:
            f.write(case.model_dump_json() + "\n")

    # 2. Save summary.json
    json_path = output_dir / "summary.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    # 3. Save summary.md
    md_path = output_dir / "summary.md"
    md_content = generate_error_summary_md(summary)
    md_path.write_text(md_content, encoding="utf-8")

    # 4. Save decision_memo.md (Exit Gate deliverable)
    memo_path = output_dir / "decision_memo.md"
    memo_content = generate_decision_memo(summary)
    memo_path.write_text(memo_content, encoding="utf-8")

    # 5. Save slices/ directory
    slices_dir = output_dir / "slices"
    slices_dir.mkdir(parents=True, exist_ok=True)
    slices_data = summary.get("slices", {})
    if isinstance(slices_data, dict):
        for slice_dim, dim_stats in slices_data.items():
            slice_file = slices_dir / f"{slice_dim}.json"
            with slice_file.open("w", encoding="utf-8") as f:
                json.dump(dim_stats, f, indent=2)


def load_labeled_cases(path: Path) -> list[LabeledCase]:
    """Load labeled cases from a labeled_cases.jsonl file, preserving order."""
    cases: list[LabeledCase] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                cases.append(LabeledCase.model_validate(json.loads(line)))
    return cases


def apply_manual_label(
    analysis_dir: Path,
    case_id: str,
    primary_error: str | None = None,
    secondary_errors: tuple[str, ...] | None = None,
    reviewer_notes: str | None = None,
) -> LabeledCase:
    """Persist a reviewer's correction to a case's error label.

    Rewrites labeled_cases.jsonl with the correction and regenerates summary.json,
    summary.md, and decision_memo.md from the corrected labels. Slice buckets are
    unaffected by relabeling (they depend on execution_correct, not primary_error),
    so the existing slice breakdown is carried forward unchanged.
    """
    labels_path = analysis_dir / "labeled_cases.jsonl"
    labeled_cases = load_labeled_cases(labels_path)

    updated: LabeledCase | None = None
    for idx, case in enumerate(labeled_cases):
        if case.case_id != case_id:
            continue
        updates: dict[str, Any] = {"is_manual": True}
        if primary_error is not None:
            updates["primary_error"] = primary_error
        if secondary_errors is not None:
            updates["secondary_errors"] = secondary_errors
        if reviewer_notes is not None:
            updates["reviewer_notes"] = reviewer_notes
        updated = case.model_copy(update=updates)
        labeled_cases[idx] = updated
        break

    if updated is None:
        raise KeyError(f"case_id {case_id!r} not found in {labels_path}")

    summary_path = analysis_dir / "summary.json"
    existing_summary = (
        json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    )
    slice_summary = existing_summary.get("slices", {})

    summary = generate_error_summary_json(labeled_cases, slice_summary)
    save_error_analysis_artifacts(analysis_dir, labeled_cases, summary)
    return updated


def _load_jsonl_by_case_id(path: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return records
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                item = json.loads(line)
                records[item["case_id"]] = item
    return records


def _retrieved_tables_from_grounding(grounding_record: dict[str, Any]) -> list[str] | None:
    if "retrieved_tables" in grounding_record:
        return list(grounding_record["retrieved_tables"])

    grounding = grounding_record.get("grounding")
    if not isinstance(grounding, dict):
        return None

    tables = grounding.get("tables")
    if not isinstance(tables, list):
        return None

    names: list[str] = []
    for table in tables:
        if isinstance(table, str):
            names.append(table)
        elif isinstance(table, dict) and isinstance(table.get("name"), str):
            names.append(table["name"])
    return names


def _retrieved_columns_from_grounding(grounding_record: dict[str, Any]) -> list[str] | None:
    if "retrieved_columns" in grounding_record:
        return list(grounding_record["retrieved_columns"])

    grounding = grounding_record.get("grounding")
    if not isinstance(grounding, dict):
        return None

    columns = grounding.get("columns")
    if not isinstance(columns, list):
        return None

    names: list[str] = []
    for column in columns:
        if isinstance(column, str):
            names.append(column)
        elif isinstance(column, dict) and isinstance(column.get("column_name"), str):
            names.append(column["column_name"])
    return names


def _grounding_metadata(grounding_record: dict[str, Any]) -> dict[str, Any]:
    grounding = grounding_record.get("grounding")
    if isinstance(grounding, dict):
        metadata = grounding.get("metadata")
        if isinstance(metadata, dict):
            return metadata
    return {}


def _metadata_value(
    key: str,
    primary: dict[str, Any],
    fallback: dict[str, Any],
    default: Any,
) -> Any:
    if key in primary:
        return primary[key]
    if key in fallback:
        return fallback[key]

    primary_metadata = primary.get("metadata", {})
    fallback_metadata = fallback.get("metadata", {})
    if isinstance(primary_metadata, dict) and key in primary_metadata:
        return primary_metadata[key]
    if isinstance(fallback_metadata, dict) and key in fallback_metadata:
        return fallback_metadata[key]
    return default


def analyze_run_directory(
    run_dir: Path,
    output_dir: Path | None = None,
    catalogs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Analyze an experiment run directory and generate error analysis artifacts.

    ``catalogs`` (a ``DatabaseCatalog`` per ``database_id``) is optional. When
    given, each case is additionally classified into the Phase 7A/7B
    fine-grained join-relationship slice (``1_hop_join``, ``2_hop_join``,
    ``3_plus_hop_join``, ``multiple_fk_ambiguity``, ``bridge_table_required``)
    via ``join_slices.classify_join_relationship_slice``; without it, only the
    coarse ``table_slice``/``join_depth`` dimensions are available, and the
    Phase 7A/7B gates fall back to those instead.
    """
    from chatsql.analysis.automatic_rules import auto_label_case
    from chatsql.analysis.join_slices import classify_join_relationship_slice
    from chatsql.analysis.slices import aggregate_slice_performance, slice_case
    from chatsql.domain.gold_case import GoldCase
    from chatsql.domain.inference_case import InferenceCase
    from chatsql.domain.result import ExecutionResult, Prediction

    predictions_path = run_dir / "predictions.jsonl"
    executions_path = run_dir / "executions.jsonl"
    groundings_path = run_dir / "groundings.jsonl"
    evaluated_cases_path = run_dir / "evaluated_cases.jsonl"

    if not evaluated_cases_path.exists() and (
        not predictions_path.exists() or not executions_path.exists()
    ):
        raise FileNotFoundError(
            f"Run directory {run_dir} missing evaluated_cases.jsonl or predictions/executions JSONL"
        )

    evaluated_by_id = _load_jsonl_by_case_id(evaluated_cases_path)
    preds_by_id = _load_jsonl_by_case_id(predictions_path)
    execs_by_id = _load_jsonl_by_case_id(executions_path)
    groundings_by_id = _load_jsonl_by_case_id(groundings_path)

    labeled_cases: list[LabeledCase] = []
    slice_records: list[dict[str, Any]] = []

    source_by_id = evaluated_by_id or preds_by_id
    for case_id, source_dict in source_by_id.items():
        pred_dict = preds_by_id.get(case_id, source_dict)
        exec_dict = execs_by_id.get(case_id, source_dict)
        gr_dict = groundings_by_id.get(case_id, {})

        db_id = _metadata_value("database_id", source_dict, exec_dict, "unknown")
        question = _metadata_value("question", source_dict, exec_dict, "")
        gold_sql = _metadata_value("gold_sql", source_dict, exec_dict, "")
        gold_tables = _metadata_value("gold_tables", source_dict, exec_dict, ())
        gold_columns = _metadata_value("gold_columns", source_dict, exec_dict, ())
        retrieved_tables = _retrieved_tables_from_grounding(gr_dict)
        retrieved_columns = _retrieved_columns_from_grounding(gr_dict)
        grounding_meta = _grounding_metadata(gr_dict)

        case = InferenceCase(case_id=case_id, question=question, database_id=db_id)
        gold = GoldCase(
            case_id=case_id,
            gold_sql=gold_sql,
            gold_tables=tuple(gold_tables),
            gold_columns=tuple(gold_columns),
        )
        pred = Prediction(
            case_id=case_id,
            predicted_sql=_metadata_value("predicted_sql", source_dict, pred_dict, ""),
            latency_seconds=_metadata_value("latency_seconds", source_dict, pred_dict, None),
        )
        execution = ExecutionResult(
            case_id=case_id,
            executed=_metadata_value("executed", source_dict, exec_dict, False),
            rows=exec_dict.get("rows", []),
            row_count=exec_dict.get("row_count"),
            error=_metadata_value("error", source_dict, exec_dict, None),
            error_kind=exec_dict.get("error_kind"),
        )
        grounding_metadata: dict[str, Any] = {}
        if retrieved_tables is not None:
            grounding_metadata["retrieved_tables"] = retrieved_tables
        if retrieved_columns is not None:
            grounding_metadata["retrieved_columns"] = retrieved_columns

        labeled = auto_label_case(
            case=case,
            gold=gold,
            prediction=pred,
            execution=execution,
            execution_correct=_metadata_value("execution_correct", source_dict, exec_dict, None),
            grounding_metadata=grounding_metadata,
        )

        labeled_cases.append(labeled)

        # Compute slices
        ret_cnt = len(retrieved_tables) if retrieved_tables is not None else None
        gold_cnt = len(gold_tables) if gold_tables else None
        catalog_table_count = grounding_meta.get("catalog_table_count")
        if catalog_table_count is None:
            catalog_table_count = _metadata_value(
                "catalog_table_count", source_dict, pred_dict, None
            )
        join_relationship: str | None = None
        catalog = catalogs.get(db_id) if catalogs else None
        if catalog is not None:
            try:
                join_relationship = classify_join_relationship_slice(case, gold, catalog)
            except Exception:
                join_relationship = None

        sl = slice_case(
            labeled_case=labeled,
            table_count_in_catalog=catalog_table_count,
            retrieved_table_count=ret_cnt,
            gold_table_count=gold_cnt,
            join_relationship=join_relationship,
        )
        slice_records.append(sl)

    slice_summary = aggregate_slice_performance(labeled_cases, slice_records)
    summary = generate_error_summary_json(labeled_cases, slice_summary)

    target_out = output_dir if output_dir is not None else run_dir / "error_analysis"
    save_error_analysis_artifacts(target_out, labeled_cases, summary)

    return summary

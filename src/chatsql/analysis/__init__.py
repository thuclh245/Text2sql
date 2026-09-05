"""Analysis module for CHATSQL Phase 5: Error Taxonomy, Diagnostic Rules, Slices, and Reports."""

from __future__ import annotations

from chatsql.analysis.automatic_rules import auto_label_case
from chatsql.analysis.case_view import export_cases_for_review, render_case_for_review
from chatsql.analysis.compare import (
    compare_error_runs,
    compare_run_directories,
    format_error_comparison_md,
)
from chatsql.analysis.reports import (
    analyze_run_directory,
    apply_manual_label,
    generate_decision_memo,
    generate_error_summary_json,
    generate_error_summary_md,
    load_labeled_cases,
    recommend_next_research_phase,
    save_error_analysis_artifacts,
)
from chatsql.analysis.slices import aggregate_slice_performance, slice_case
from chatsql.analysis.taxonomy import (
    TAXONOMY_MAP,
    ErrorCategory,
    ErrorCodeInfo,
    LabeledCase,
)

__all__ = [
    "TAXONOMY_MAP",
    "ErrorCategory",
    "ErrorCodeInfo",
    "LabeledCase",
    "aggregate_slice_performance",
    "analyze_run_directory",
    "apply_manual_label",
    "auto_label_case",
    "compare_error_runs",
    "compare_run_directories",
    "export_cases_for_review",
    "format_error_comparison_md",
    "generate_decision_memo",
    "generate_error_summary_json",
    "generate_error_summary_md",
    "load_labeled_cases",
    "recommend_next_research_phase",
    "render_case_for_review",
    "save_error_analysis_artifacts",
    "slice_case",
]

"""Analysis module for CHATSQL error taxonomy, diagnostic rules, slices, and reports."""

from __future__ import annotations

from chatsql.analysis.automatic_rules import auto_label_case
from chatsql.analysis.case_view import export_cases_for_review, render_case_for_review
from chatsql.analysis.compare import (
    compare_error_runs,
    compare_run_directories,
    format_error_comparison_md,
)
from chatsql.analysis.relationship_ablation_gate import (
    format_relationship_ablation_gate_report_md,
    generate_relationship_ablation_gate_report,
    save_relationship_ablation_gate_report,
)
from chatsql.analysis.relationship_benchmark_gate import (
    format_relationship_benchmark_gate_report_md,
    generate_relationship_benchmark_gate_report,
    save_relationship_benchmark_gate_report,
)
from chatsql.analysis.relationship_error_analysis import (
    classify_relationship_error,
    format_relationship_error_analysis_report_md,
    generate_relationship_error_analysis_report,
    save_relationship_error_analysis_report,
)
from chatsql.analysis.relationship_slice_metrics import (
    format_relationship_hardening_gate_report_md,
    format_relationship_slice_metrics_report_md,
    generate_relationship_hardening_gate_report,
    generate_relationship_slice_metrics_report,
    save_relationship_hardening_gate_report,
    save_relationship_slice_metrics_report,
)
from chatsql.analysis.reports import (
    analyze_run_directory,
    apply_manual_label,
    generate_decision_memo,
    generate_error_summary_json,
    generate_error_summary_md,
    load_labeled_cases,
    recommend_next_research_track,
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
    "classify_relationship_error",
    "compare_error_runs",
    "compare_run_directories",
    "export_cases_for_review",
    "format_error_comparison_md",
    "format_relationship_ablation_gate_report_md",
    "format_relationship_benchmark_gate_report_md",
    "format_relationship_error_analysis_report_md",
    "format_relationship_hardening_gate_report_md",
    "format_relationship_slice_metrics_report_md",
    "generate_decision_memo",
    "generate_error_summary_json",
    "generate_error_summary_md",
    "generate_relationship_ablation_gate_report",
    "generate_relationship_benchmark_gate_report",
    "generate_relationship_error_analysis_report",
    "generate_relationship_hardening_gate_report",
    "generate_relationship_slice_metrics_report",
    "load_labeled_cases",
    "recommend_next_research_track",
    "render_case_for_review",
    "save_error_analysis_artifacts",
    "save_relationship_ablation_gate_report",
    "save_relationship_benchmark_gate_report",
    "save_relationship_error_analysis_report",
    "save_relationship_hardening_gate_report",
    "save_relationship_slice_metrics_report",
    "slice_case",
]

"""Unit tests for the error analysis module."""

from __future__ import annotations

import json
from pathlib import Path

from chatsql.analysis import (
    TAXONOMY_MAP,
    ErrorCategory,
    LabeledCase,
    analyze_run_directory,
    apply_manual_label,
    auto_label_case,
    classify_relationship_error,
    compare_error_runs,
    export_cases_for_review,
    format_relationship_ablation_gate_report_md,
    format_relationship_benchmark_gate_report_md,
    format_relationship_error_analysis_report_md,
    generate_decision_memo,
    generate_relationship_ablation_gate_report,
    generate_relationship_benchmark_gate_report,
    generate_relationship_error_analysis_report,
    load_labeled_cases,
    recommend_next_research_track,
    render_case_for_review,
    save_relationship_ablation_gate_report,
    save_relationship_benchmark_gate_report,
    save_relationship_error_analysis_report,
    slice_case,
)
from chatsql.analysis.automatic_rules import extract_where_literals
from chatsql.domain.catalog import ColumnInfo, DatabaseCatalog, TableInfo
from chatsql.domain.gold_case import GoldCase
from chatsql.domain.inference_case import InferenceCase
from chatsql.domain.result import ExecutionResult, Prediction


def test_taxonomy_map_integrity() -> None:
    assert "E01" in TAXONOMY_MAP
    assert TAXONOMY_MAP["E01"].category == ErrorCategory.RETRIEVAL_GROUNDING
    assert "E10" in TAXONOMY_MAP
    assert TAXONOMY_MAP["E10"].category == ErrorCategory.RELATIONSHIP_JOIN
    assert "E21" in TAXONOMY_MAP
    assert TAXONOMY_MAP["E21"].category == ErrorCategory.BUSINESS_SEMANTIC
    assert "E41" in TAXONOMY_MAP
    assert TAXONOMY_MAP["E41"].category == ErrorCategory.SQL_GENERATION


def test_auto_label_case_correct() -> None:
    case = InferenceCase(case_id="q1", question="List orders", database_id="db1")
    gold = GoldCase(case_id="q1", gold_sql="SELECT * FROM orders", gold_tables=("orders",))
    pred = Prediction(case_id="q1", predicted_sql="SELECT * FROM orders")
    exec_res = ExecutionResult(case_id="q1", executed=True, rows=[[1]])

    labeled = auto_label_case(case, gold, pred, exec_res, execution_correct=True)
    assert labeled.execution_correct is True
    assert labeled.primary_error == "NONE"
    assert labeled.primary_category == ErrorCategory.NONE


def test_auto_label_case_syntax_error() -> None:
    case = InferenceCase(case_id="q2", question="List orders", database_id="db1")
    gold = GoldCase(case_id="q2", gold_sql="SELECT * FROM orders")
    pred = Prediction(case_id="q2", predicted_sql="SELEC * FORM orders")
    exec_res = ExecutionResult(
        case_id="q2", executed=False, error="Syntax error near SELEC", error_kind="invalid_sql"
    )

    labeled = auto_label_case(case, gold, pred, exec_res)
    assert labeled.execution_correct is False
    assert labeled.primary_error == "E41"
    assert labeled.primary_category == ErrorCategory.SQL_GENERATION


def test_auto_label_case_missing_table() -> None:
    case = InferenceCase(case_id="q3", question="Find customer orders", database_id="db1")
    gold = GoldCase(
        case_id="q3",
        gold_sql="SELECT * FROM customers JOIN orders ON customers.id = orders.cust_id",
        gold_tables=("customers", "orders"),
    )
    pred = Prediction(case_id="q3", predicted_sql="SELECT * FROM customers")
    exec_res = ExecutionResult(case_id="q3", executed=True, rows=[])

    labeled = auto_label_case(case, gold, pred, exec_res)
    assert labeled.execution_correct is False
    assert labeled.primary_error == "E01"
    assert labeled.primary_category == ErrorCategory.RETRIEVAL_GROUNDING
    assert "orders" in labeled.metadata.get("missing_tables", [])


def test_auto_label_case_missing_join() -> None:
    case = InferenceCase(case_id="q4", question="Count orders per customer", database_id="db1")
    gold = GoldCase(
        case_id="q4",
        gold_sql=(
            "SELECT customers.name, COUNT(*) FROM customers "
            "JOIN orders ON customers.id = orders.cust_id "
            "GROUP BY customers.name"
        ),
        gold_tables=("customers", "orders"),
    )
    # Prediction has both tables in query but missing JOIN operator
    pred = Prediction(
        case_id="q4",
        predicted_sql=(
            "SELECT customers.name, COUNT(*) FROM customers, orders GROUP BY customers.name"
        ),
    )
    exec_res = ExecutionResult(case_id="q4", executed=True, rows=[])

    labeled = auto_label_case(case, gold, pred, exec_res)
    assert labeled.execution_correct is False
    assert labeled.primary_error == "E10"
    assert labeled.primary_category == ErrorCategory.RELATIONSHIP_JOIN


def test_auto_label_case_wrong_aggregation() -> None:
    case = InferenceCase(case_id="q5", question="Total sales amount", database_id="db1")
    gold = GoldCase(case_id="q5", gold_sql="SELECT SUM(amount) FROM sales", gold_tables=("sales",))
    pred = Prediction(case_id="q5", predicted_sql="SELECT COUNT(amount) FROM sales")
    exec_res = ExecutionResult(case_id="q5", executed=True, rows=[[10]])

    labeled = auto_label_case(case, gold, pred, exec_res)
    assert labeled.execution_correct is False
    assert labeled.primary_error == "E21"
    assert labeled.primary_category == ErrorCategory.BUSINESS_SEMANTIC


def test_render_case_for_review() -> None:
    case_label = LabeledCase(
        case_id="q1",
        database_id="shop",
        question="What is the total price?",
        predicted_sql="SELECT COUNT(price) FROM orders",
        gold_sql="SELECT SUM(price) FROM orders",
        execution_correct=False,
        primary_error="E21",
    )
    text = render_case_for_review(case_label, retrieved_tables=("orders",))
    assert "CASE ID: q1" in text
    assert "PRE-LABEL: [E21]" in text
    assert "SELECT SUM(price) FROM orders" in text


def test_decision_rules_recommendation() -> None:
    rec_grounding = recommend_next_research_track(
        {"Retrieval / Grounding": 60.0, "Relationship / Join": 40.0}
    )
    assert rec_grounding["recommended_track"] == "grounding_retrieval_research"

    rec_join = recommend_next_research_track(
        {"Retrieval / Grounding": 20.0, "Relationship / Join": 70.0}
    )
    assert rec_join["recommended_track"] == "join_relationship_research"

    rec_semantic = recommend_next_research_track(
        {"Business / Semantic": 80.0, "SQL Generation": 20.0}
    )
    assert rec_semantic["recommended_track"] == "semantic_model_research"


def test_slice_case() -> None:
    labeled = LabeledCase(
        case_id="c1",
        database_id="db1",
        question="Q",
        predicted_sql="SELECT * FROM a JOIN b ON a.id=b.a_id JOIN c ON b.id=c.b_id",
        gold_sql="SELECT * FROM a JOIN b ON a.id=b.a_id JOIN c ON b.id=c.b_id",
        execution_correct=True,
        primary_error="NONE",
    )
    sl = slice_case(labeled, table_count_in_catalog=20, retrieved_table_count=8, gold_table_count=3)
    assert sl["table_slice"] == "multi_table"
    assert sl["join_depth"] == "2+_joins"
    assert "large" in sl["schema_size"]
    assert sl["high_noise_retrieval"] is True


def test_analyze_run_directory(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_001"
    run_dir.mkdir()

    preds = [
        {"case_id": "q1", "predicted_sql": "SELECT * FROM orders"},
        {"case_id": "q2", "predicted_sql": "SELECT * FROM users"},
    ]
    execs = [
        {"case_id": "q1", "executed": True, "rows": [[1]]},
        {"case_id": "q2", "executed": True, "rows": []},
    ]
    evaluated = [
        {
            "case_id": "q1",
            "database_id": "shop",
            "question": "Q1",
            "predicted_sql": "SELECT * FROM orders",
            "executed": True,
            "execution_correct": True,
            "gold_sql": "SELECT * FROM orders",
            "gold_tables": ["orders"],
            "gold_columns": [],
        },
        {
            "case_id": "q2",
            "database_id": "shop",
            "question": "Q2",
            "predicted_sql": "SELECT * FROM users",
            "executed": True,
            "execution_correct": False,
            "gold_sql": "SELECT * FROM orders JOIN users ON orders.user_id=users.id",
            "gold_tables": ["orders", "users"],
            "gold_columns": [],
        },
    ]
    groundings = [
        {
            "case_id": "q1",
            "grounding": {"tables": [{"name": "orders"}], "columns": []},
        },
        {
            "case_id": "q2",
            "grounding": {"tables": [{"name": "users"}], "columns": []},
        },
    ]

    with (run_dir / "predictions.jsonl").open("w", encoding="utf-8") as f:
        for p in preds:
            f.write(json.dumps(p) + "\n")
    with (run_dir / "executions.jsonl").open("w", encoding="utf-8") as f:
        for e in execs:
            f.write(json.dumps(e) + "\n")
    with (run_dir / "evaluated_cases.jsonl").open("w", encoding="utf-8") as f:
        for e in evaluated:
            f.write(json.dumps(e) + "\n")
    with (run_dir / "groundings.jsonl").open("w", encoding="utf-8") as f:
        for g in groundings:
            f.write(json.dumps(g) + "\n")

    summary = analyze_run_directory(run_dir)
    assert summary["total_cases"] == 2
    assert summary["correct_cases"] == 1
    assert summary["accuracy_pct"] == 50.0
    assert summary["error_budget_pct"] == {"Retrieval / Grounding": 100.0}
    assert (run_dir / "error_analysis" / "summary.json").exists()
    assert (run_dir / "error_analysis" / "summary.md").exists()
    assert (run_dir / "error_analysis" / "labeled_cases.jsonl").exists()


def test_compare_error_runs() -> None:
    labels_a = [
        LabeledCase(
            case_id="q1",
            database_id="db",
            question="Q1",
            predicted_sql="S1",
            gold_sql="S1",
            execution_correct=True,
            primary_error="NONE",
        ),
        LabeledCase(
            case_id="q2",
            database_id="db",
            question="Q2",
            predicted_sql="S2",
            gold_sql="S2",
            execution_correct=False,
            primary_error="E01",
        ),
    ]
    labels_b = [
        LabeledCase(
            case_id="q1",
            database_id="db",
            question="Q1",
            predicted_sql="S1",
            gold_sql="S1",
            execution_correct=True,
            primary_error="NONE",
        ),
        LabeledCase(
            case_id="q2",
            database_id="db",
            question="Q2",
            predicted_sql="S2",
            gold_sql="S2",
            execution_correct=True,
            primary_error="NONE",
        ),
    ]

    comp = compare_error_runs(labels_a, labels_b, "Run A", "Run B")
    assert comp["accuracy_a"] == 50.0
    assert comp["accuracy_b"] == 100.0
    assert comp["accuracy_diff"] == 50.0


def test_generate_relationship_benchmark_gate_report_compares_runs(tmp_path: Path) -> None:
    full_schema_run_dir = tmp_path / "full_schema_run"
    relationship_aware_run_dir = tmp_path / "relationship_aware_run"
    full_schema_run_dir.mkdir()
    relationship_aware_run_dir.mkdir()

    full_schema_summary = {
        "total_cases": 4,
        "correct_cases": 2,
        "accuracy_pct": 50.0,
        "slices": {
            "table_slice": {
                "single_table": {"total": 2, "correct": 2, "errors": 0, "accuracy_pct": 100.0},
                "multi_table": {"total": 2, "correct": 0, "errors": 2, "accuracy_pct": 0.0},
            }
        },
    }
    relationship_aware_summary = {
        "total_cases": 4,
        "correct_cases": 3,
        "accuracy_pct": 75.0,
        "slices": {
            "table_slice": {
                "single_table": {"total": 2, "correct": 2, "errors": 0, "accuracy_pct": 100.0},
                "multi_table": {"total": 2, "correct": 1, "errors": 1, "accuracy_pct": 50.0},
            }
        },
    }
    (full_schema_run_dir / "error_analysis").mkdir()
    (relationship_aware_run_dir / "error_analysis").mkdir()
    (full_schema_run_dir / "error_analysis" / "summary.json").write_text(
        json.dumps(full_schema_summary),
        encoding="utf-8",
    )
    (relationship_aware_run_dir / "error_analysis" / "summary.json").write_text(
        json.dumps(relationship_aware_summary),
        encoding="utf-8",
    )
    (full_schema_run_dir / "metrics.json").write_text(
        json.dumps({"relationship_path_coverage": 0.2, "relationship_edge_recall": 0.3}),
        encoding="utf-8",
    )
    (relationship_aware_run_dir / "metrics.json").write_text(
        json.dumps({"relationship_path_coverage": 0.6, "relationship_edge_recall": 0.4}),
        encoding="utf-8",
    )

    report = generate_relationship_benchmark_gate_report(
        full_schema_run_dir,
        relationship_aware_run_dir,
    )
    assert report["overall"]["accuracy_delta_pct"] == 25.0
    assert report["single_table_delta"]["accuracy_delta_pct"] == 0.0
    assert report["gate"]["passed"] is True

    md = format_relationship_benchmark_gate_report_md(report)
    assert "Phase 7A Benchmark Gate Report" in md
    assert "relationship_path_coverage" in md

    output_dir = tmp_path / "gate"
    save_relationship_benchmark_gate_report(report, output_dir)
    assert (output_dir / "relationship_benchmark_gate_report.json").exists()
    assert (output_dir / "relationship_benchmark_gate_report.md").exists()


def test_auto_label_missing_column() -> None:
    case = InferenceCase(case_id="q_col", question="Get order status", database_id="db1")
    gold = GoldCase(
        case_id="q_col",
        gold_sql="SELECT id, status FROM orders",
        gold_tables=("orders",),
        gold_columns=("id", "status"),
    )
    pred = Prediction(case_id="q_col", predicted_sql="SELECT id FROM orders")
    exec_res = ExecutionResult(case_id="q_col", executed=True, rows=[[1]])

    labeled = auto_label_case(case, gold, pred, exec_res)
    assert labeled.execution_correct is False
    assert labeled.primary_error == "E02"
    assert labeled.primary_category == ErrorCategory.RETRIEVAL_GROUNDING
    assert "status" in labeled.metadata.get("missing_columns", [])


def test_auto_label_join_key_mismatch() -> None:
    case = InferenceCase(case_id="q_join", question="Join orders and users", database_id="db1")
    gold = GoldCase(
        case_id="q_join",
        gold_sql="SELECT * FROM orders JOIN users ON orders.user_id = users.id",
        gold_tables=("orders", "users"),
    )
    pred = Prediction(
        case_id="q_join",
        predicted_sql="SELECT * FROM orders JOIN users ON orders.id = users.id",
    )
    exec_res = ExecutionResult(case_id="q_join", executed=True, rows=[])

    labeled = auto_label_case(case, gold, pred, exec_res)
    assert labeled.execution_correct is False
    assert labeled.primary_error == "E12"
    assert labeled.primary_category == ErrorCategory.RELATIONSHIP_JOIN


def test_auto_label_time_semantics() -> None:
    case = InferenceCase(case_id="q_time", question="Orders in 2024", database_id="db1")
    gold = GoldCase(
        case_id="q_time",
        gold_sql="SELECT * FROM orders WHERE strftime('%Y', order_date) = '2024'",
        gold_tables=("orders",),
    )
    pred = Prediction(
        case_id="q_time",
        predicted_sql="SELECT * FROM orders WHERE order_date = '2024'",
    )
    exec_res = ExecutionResult(case_id="q_time", executed=True, rows=[])

    labeled = auto_label_case(case, gold, pred, exec_res)
    assert labeled.execution_correct is False
    assert labeled.primary_error == "E23"
    assert labeled.primary_category == ErrorCategory.BUSINESS_SEMANTIC


def test_auto_label_wrong_filter_column() -> None:
    case = InferenceCase(case_id="q_filter", question="Active users", database_id="db1")
    gold = GoldCase(
        case_id="q_filter",
        gold_sql="SELECT * FROM users WHERE is_active = 1",
        gold_tables=("users",),
    )
    pred = Prediction(
        case_id="q_filter",
        predicted_sql="SELECT * FROM users WHERE status = 1",
    )
    exec_res = ExecutionResult(case_id="q_filter", executed=True, rows=[])

    labeled = auto_label_case(case, gold, pred, exec_res)
    assert labeled.execution_correct is False
    assert labeled.primary_error == "E30"
    assert labeled.primary_category == ErrorCategory.VALUE_FILTER


def test_decision_memo_format_satisfies_exit_gate() -> None:
    summary = {
        "total_cases": 100,
        "correct_cases": 40,
        "incorrect_cases": 60,
        "accuracy_pct": 40.0,
        "error_budget_pct": {
            "Retrieval / Grounding": 55.0,
            "Relationship / Join": 25.0,
            "Business / Semantic": 15.0,
            "SQL Generation": 5.0,
        },
        "slices": {
            "table_slice": {
                "multi_table": {"total": 50, "correct": 10, "accuracy_pct": 20.0},
                "single_table": {"total": 50, "correct": 30, "accuracy_pct": 60.0},
            }
        },
        "decision": {
            "dominant_category": "Retrieval / Grounding",
            "dominant_percentage": 55.0,
            "recommended_track": "grounding_retrieval_research",
            "recommended_track_name": "Grounding and Retrieval Research",
            "reason": "Retrieval dominates error budget.",
        },
    }
    memo = generate_decision_memo(summary, baseline_name="B0 Full-Schema Control")
    # Must enforce all 7 Exit Gate template fields (Section 7)
    assert "Observed bottleneck:" in memo
    assert "Evidence:" in memo
    assert "Affected slices:" in memo
    assert "Baseline:" in memo
    assert "Hypothesis candidates:" in memo
    assert "Why this is not only engineering:" in memo
    assert "Next research track:" in memo
    assert "grounding_retrieval_research" in memo


def test_save_error_analysis_artifacts_writes_all_files(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_artifacts_test"
    run_dir.mkdir()

    preds = [
        {"case_id": "c1", "predicted_sql": "SELECT 1"},
        {"case_id": "c2", "predicted_sql": "SELECT 1"},
    ]
    execs = [{"case_id": "c1", "executed": True}, {"case_id": "c2", "executed": True}]
    evaluated = [
        {
            "case_id": "c1",
            "database_id": "db1",
            "question": "Q1",
            "predicted_sql": "SELECT 1",
            "executed": True,
            "execution_correct": True,
            "gold_sql": "SELECT 1",
            "gold_tables": ["t1"],
            "gold_columns": [],
        },
        {
            "case_id": "c2",
            "database_id": "db1",
            "question": "Q2",
            "predicted_sql": "SELECT 1",
            "executed": True,
            "execution_correct": False,
            "gold_sql": "SELECT * FROM t2",
            "gold_tables": ["t2"],
            "gold_columns": [],
        },
    ]
    with (run_dir / "predictions.jsonl").open("w", encoding="utf-8") as f:
        for p in preds:
            f.write(json.dumps(p) + "\n")
    with (run_dir / "executions.jsonl").open("w", encoding="utf-8") as f:
        for e in execs:
            f.write(json.dumps(e) + "\n")
    with (run_dir / "evaluated_cases.jsonl").open("w", encoding="utf-8") as f:
        for e in evaluated:
            f.write(json.dumps(e) + "\n")

    summary = analyze_run_directory(run_dir)
    assert summary["total_cases"] == 2
    out_dir = run_dir / "error_analysis"
    assert (out_dir / "labeled_cases.jsonl").exists()
    assert (out_dir / "summary.json").exists()
    assert (out_dir / "summary.md").exists()
    assert (out_dir / "decision_memo.md").exists()
    assert (out_dir / "slices").is_dir()
    assert (out_dir / "slices" / "table_slice.json").exists()


def test_export_cases_for_review(tmp_path: Path) -> None:
    cases = [
        LabeledCase(
            case_id="c1",
            database_id="db1",
            question="Q1",
            predicted_sql="SELECT 1",
            gold_sql="SELECT 2",
            execution_correct=False,
            primary_error="E01",
        )
    ]
    out_file = tmp_path / "review.md"
    export_cases_for_review(cases, out_file)
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert "Manual Audit Review Sheet" in content
    assert "c1" in content


def test_cli_analysis_commands(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from chatsql.cli import app

    runner = CliRunner()
    run_dir = tmp_path / "cli_run"
    run_dir.mkdir()

    preds = [{"case_id": "c1", "predicted_sql": "SELECT 1"}]
    execs = [{"case_id": "c1", "executed": True}]
    evaluated = [
        {
            "case_id": "c1",
            "database_id": "db1",
            "question": "Q1",
            "predicted_sql": "SELECT 1",
            "executed": True,
            "execution_correct": True,
            "gold_sql": "SELECT 1",
            "gold_tables": ["t1"],
            "gold_columns": [],
        }
    ]
    with (run_dir / "predictions.jsonl").open("w", encoding="utf-8") as f:
        for p in preds:
            f.write(json.dumps(p) + "\n")
    with (run_dir / "executions.jsonl").open("w", encoding="utf-8") as f:
        for e in execs:
            f.write(json.dumps(e) + "\n")
    with (run_dir / "evaluated_cases.jsonl").open("w", encoding="utf-8") as f:
        for e in evaluated:
            f.write(json.dumps(e) + "\n")

    # 1. chatsql analysis run
    res_run = runner.invoke(app, ["analysis", "run", "--run-dir", str(run_dir)])
    assert res_run.exit_code == 0
    assert "Error Analysis complete" in res_run.output

    # 2. chatsql analysis view
    res_view = runner.invoke(app, ["analysis", "view", "--run-dir", str(run_dir)])
    assert res_view.exit_code == 0
    assert "CASE ID: c1" in res_view.output

    # 3. chatsql analysis memo
    res_memo = runner.invoke(app, ["analysis", "memo", "--run-dir", str(run_dir)])
    assert res_memo.exit_code == 0
    assert "Scientific Exit Gate Memo" in res_memo.output

    # 4. chatsql analysis label
    res_label = runner.invoke(
        app,
        [
            "analysis",
            "label",
            "--run-dir",
            str(run_dir),
            "--case-id",
            "c1",
            "--primary-error",
            "E90",
            "--notes",
            "Reviewed manually, evaluator false negative.",
        ],
    )
    assert res_label.exit_code == 0, res_label.output
    assert "is_manual=True" in res_label.output

    labels_file = run_dir / "error_analysis" / "labeled_cases.jsonl"
    saved = load_labeled_cases(labels_file)
    assert saved[0].primary_error == "E90"
    assert saved[0].is_manual is True
    assert saved[0].reviewer_notes == "Reviewed manually, evaluator false negative."


def test_cli_relationship_benchmark_gate_command(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from chatsql.cli import app

    full_schema_run_dir = tmp_path / "full_schema_run"
    relationship_aware_run_dir = tmp_path / "relationship_aware_run"
    for run_dir, correct_cases, multi_accuracy, path_coverage in (
        (full_schema_run_dir, 2, 0.0, 0.1),
        (relationship_aware_run_dir, 3, 50.0, 0.5),
    ):
        analysis_dir = run_dir / "error_analysis"
        analysis_dir.mkdir(parents=True)
        summary = {
            "total_cases": 4,
            "correct_cases": correct_cases,
            "accuracy_pct": correct_cases / 4 * 100,
            "slices": {
                "table_slice": {
                    "single_table": {
                        "total": 2,
                        "correct": 2,
                        "errors": 0,
                        "accuracy_pct": 100.0,
                    },
                    "multi_table": {
                        "total": 2,
                        "correct": 1 if multi_accuracy else 0,
                        "errors": 1 if multi_accuracy else 2,
                        "accuracy_pct": multi_accuracy,
                    },
                }
            },
        }
        (analysis_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
        (run_dir / "metrics.json").write_text(
            json.dumps({"relationship_path_coverage": path_coverage}),
            encoding="utf-8",
        )

    output_dir = tmp_path / "phase7a"
    result = CliRunner().invoke(
        app,
        [
            "analysis",
            "phase7a-benchmark-gate",
            "--full-schema-run",
            str(full_schema_run_dir),
            "--relationship-aware-run",
            str(relationship_aware_run_dir),
            "--output-dir",
            str(output_dir),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Phase 7A gate report saved" in result.output
    assert (output_dir / "relationship_benchmark_gate_report.md").exists()


def test_relationship_ablation_gate_report_detects_targeted_drops(tmp_path: Path) -> None:
    relationship_run_dir = tmp_path / "relationship_aware"
    a1_run_dir = tmp_path / "a1"
    a2_run_dir = tmp_path / "a2"
    a3_run_dir = tmp_path / "a3"

    _write_ablation_summary(
        relationship_run_dir,
        correct_cases=18,
        multiple_fk_accuracy=75.0,
        aggregation_accuracy=80.0,
        bridge_accuracy=70.0,
        path_coverage=0.8,
    )
    _write_ablation_summary(
        a1_run_dir,
        correct_cases=16,
        multiple_fk_accuracy=65.0,
        aggregation_accuracy=80.0,
        bridge_accuracy=70.0,
        path_coverage=0.72,
    )
    _write_ablation_summary(
        a2_run_dir,
        correct_cases=16,
        multiple_fk_accuracy=75.0,
        aggregation_accuracy=60.0,
        bridge_accuracy=70.0,
        path_coverage=0.75,
    )
    _write_ablation_summary(
        a3_run_dir,
        correct_cases=15,
        multiple_fk_accuracy=75.0,
        aggregation_accuracy=80.0,
        bridge_accuracy=50.0,
        path_coverage=0.5,
    )

    report = generate_relationship_ablation_gate_report(
        relationship_aware_run_dir=relationship_run_dir,
        a1_run_dir=a1_run_dir,
        a2_run_dir=a2_run_dir,
        a3_run_dir=a3_run_dir,
    )
    md = format_relationship_ablation_gate_report_md(report)

    assert report["phase"] == "7B"
    assert report["gate"]["passed"] is True
    assert [ablation["target_drop_pct"] for ablation in report["ablations"]] == [
        10.0,
        20.0,
        20.0,
    ]
    assert "Phase 7B Ablation Gate Report" in md
    assert "`join_relationship=multiple_fk_ambiguity`" in md

    output_dir = tmp_path / "phase7b"
    save_relationship_ablation_gate_report(report, output_dir)
    assert (output_dir / "relationship_ablation_gate_report.json").exists()
    assert (output_dir / "relationship_ablation_gate_report.md").exists()


def test_relationship_ablation_gate_report_fails_missing_target_drop(tmp_path: Path) -> None:
    relationship_run_dir = tmp_path / "relationship_aware"
    a1_run_dir = tmp_path / "a1"
    a2_run_dir = tmp_path / "a2"
    a3_run_dir = tmp_path / "a3"

    for run_dir in (relationship_run_dir, a1_run_dir, a2_run_dir, a3_run_dir):
        _write_ablation_summary(
            run_dir,
            correct_cases=18,
            multiple_fk_accuracy=75.0,
            aggregation_accuracy=80.0,
            bridge_accuracy=70.0,
            path_coverage=0.8,
        )

    report = generate_relationship_ablation_gate_report(
        relationship_aware_run_dir=relationship_run_dir,
        a1_run_dir=a1_run_dir,
        a2_run_dir=a2_run_dir,
        a3_run_dir=a3_run_dir,
    )

    assert report["gate"]["passed"] is False
    assert report["ablations"][0]["gate"]["targeted_slice_drop_detected"] is False


def test_cli_relationship_ablation_gate_command(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from chatsql.cli import app

    relationship_run_dir = tmp_path / "relationship_aware"
    a1_run_dir = tmp_path / "a1"
    a2_run_dir = tmp_path / "a2"
    a3_run_dir = tmp_path / "a3"
    _write_ablation_summary(
        relationship_run_dir,
        correct_cases=18,
        multiple_fk_accuracy=75.0,
        aggregation_accuracy=80.0,
        bridge_accuracy=70.0,
        path_coverage=0.8,
    )
    _write_ablation_summary(
        a1_run_dir,
        correct_cases=16,
        multiple_fk_accuracy=65.0,
        aggregation_accuracy=80.0,
        bridge_accuracy=70.0,
        path_coverage=0.72,
    )
    _write_ablation_summary(
        a2_run_dir,
        correct_cases=16,
        multiple_fk_accuracy=75.0,
        aggregation_accuracy=60.0,
        bridge_accuracy=70.0,
        path_coverage=0.75,
    )
    _write_ablation_summary(
        a3_run_dir,
        correct_cases=15,
        multiple_fk_accuracy=75.0,
        aggregation_accuracy=80.0,
        bridge_accuracy=50.0,
        path_coverage=0.5,
    )

    output_dir = tmp_path / "phase7b"
    result = CliRunner().invoke(
        app,
        [
            "analysis",
            "phase7b-ablation-gate",
            "--relationship-aware-run",
            str(relationship_run_dir),
            "--a1-run",
            str(a1_run_dir),
            "--a2-run",
            str(a2_run_dir),
            "--a3-run",
            str(a3_run_dir),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Phase 7B ablation gate report saved" in result.output
    assert (output_dir / "relationship_ablation_gate_report.md").exists()


def _make_labeled_case(
    case_id: str,
    primary_error: str,
    secondary_errors: tuple[str, ...] = (),
    execution_correct: bool = False,
    gold_sql: str = "SELECT 1",
    database_id: str = "db1",
) -> LabeledCase:
    return LabeledCase(
        case_id=case_id,
        database_id=database_id,
        question="q",
        predicted_sql="SELECT 1",
        gold_sql=gold_sql,
        execution_correct=execution_correct,
        primary_error=primary_error,
        secondary_errors=secondary_errors,
    )


def test_classify_relationship_error_buckets() -> None:
    assert classify_relationship_error(_make_labeled_case("c1", "E01"), False) == "missing_table"
    assert classify_relationship_error(_make_labeled_case("c2", "E12"), False) == "wrong_fk"
    assert classify_relationship_error(_make_labeled_case("c3", "E10"), False) == "wrong_fk"
    assert classify_relationship_error(_make_labeled_case("c4", "E13"), False) == "fanout_grain"
    assert (
        classify_relationship_error(_make_labeled_case("c5", "E40", ("E13",)), False)
        == "fanout_grain"
    )
    assert (
        classify_relationship_error(_make_labeled_case("c6", "E40"), False)
        == "sql_generation_despite_correct_plan"
    )
    # bridge_required overrides the raw error code for join/retrieval-shaped failures.
    assert classify_relationship_error(_make_labeled_case("c7", "E01"), True) == "missing_bridge"
    assert classify_relationship_error(_make_labeled_case("c8", "E12"), True) == "missing_bridge"
    # ...but not for failures unrelated to retrieval/join/grain.
    assert (
        classify_relationship_error(_make_labeled_case("c9", "E40"), True)
        == "sql_generation_despite_correct_plan"
    )


def _write_labeled_cases(run_dir: Path, cases: list[LabeledCase]) -> None:
    analysis_dir = run_dir / "error_analysis"
    analysis_dir.mkdir(parents=True)
    with (analysis_dir / "labeled_cases.jsonl").open("w", encoding="utf-8") as f:
        for case in cases:
            f.write(case.model_dump_json() + "\n")


def test_generate_relationship_error_analysis_report_buckets_and_finds_bottleneck(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "relationship_aware_run"
    cases = [
        _make_labeled_case("m1", "E01"),
        _make_labeled_case("m2", "E01"),
        _make_labeled_case("m3", "E01"),
        _make_labeled_case("f1", "E12"),
        _make_labeled_case("g1", "E13"),
        _make_labeled_case("s1", "E40"),
        _make_labeled_case("ok1", "NONE", execution_correct=True),
    ]
    _write_labeled_cases(run_dir, cases)

    report = generate_relationship_error_analysis_report(run_dir, run_name="relationship_aware")

    assert report["phase"] == "7C"
    assert report["total_cases"] == 7
    assert report["correct_cases"] == 1
    assert report["total_incorrect"] == 6
    assert report["bridge_detection_available"] is False

    by_bucket = {b["bucket"]: b for b in report["buckets"]}
    assert by_bucket["missing_table"]["count"] == 3
    assert by_bucket["wrong_fk"]["count"] == 1
    assert by_bucket["fanout_grain"]["count"] == 1
    assert by_bucket["sql_generation_despite_correct_plan"]["count"] == 1
    assert by_bucket["missing_bridge"]["count"] == 0

    assert report["bottleneck"]["bucket"] == "missing_table"
    assert report["bottleneck"]["count"] == 3
    assert report["bottleneck"]["pct_of_incorrect"] == 50.0

    md = format_relationship_error_analysis_report_md(report)
    assert "Phase 7C Error Analysis Report" in md
    assert "Missing table" in md
    assert "Primary bottleneck:** Missing table" in md

    output_dir = tmp_path / "phase7c"
    save_relationship_error_analysis_report(report, output_dir)
    assert (output_dir / "relationship_error_analysis_report.json").exists()
    assert (output_dir / "relationship_error_analysis_report.md").exists()


def test_generate_relationship_error_analysis_report_detects_missing_bridge_with_catalog(
    tmp_path: Path,
) -> None:
    catalog = DatabaseCatalog(
        database_id="db1",
        tables=(
            TableInfo(
                name="customers",
                columns=(ColumnInfo(name="id", data_type="INTEGER", is_primary_key=True),),
            ),
            TableInfo(
                name="orders",
                columns=(
                    ColumnInfo(name="id", data_type="INTEGER", is_primary_key=True),
                    ColumnInfo(
                        name="customer_id",
                        data_type="INTEGER",
                        is_foreign_key=True,
                        references="customers.id",
                    ),
                ),
            ),
            TableInfo(
                name="order_items",
                columns=(
                    ColumnInfo(
                        name="order_id",
                        data_type="INTEGER",
                        is_foreign_key=True,
                        references="orders.id",
                    ),
                    ColumnInfo(
                        name="product_id",
                        data_type="INTEGER",
                        is_foreign_key=True,
                        references="products.id",
                    ),
                ),
            ),
            TableInfo(
                name="products",
                columns=(ColumnInfo(name="id", data_type="INTEGER", is_primary_key=True),),
            ),
        ),
    )

    bridge_gold_sql = (
        "SELECT customers.id, products.id, order_items.order_id "
        "FROM customers, products, order_items"
    )
    run_dir = tmp_path / "relationship_aware_run"
    _write_labeled_cases(
        run_dir,
        [
            _make_labeled_case("bridge1", "E01", gold_sql=bridge_gold_sql),
            _make_labeled_case("plain_missing", "E01", gold_sql="SELECT 1 FROM orders"),
        ],
    )

    report = generate_relationship_error_analysis_report(
        run_dir,
        catalogs={"db1": catalog},
    )

    assert report["bridge_detection_available"] is True
    by_bucket = {b["bucket"]: b for b in report["buckets"]}
    assert by_bucket["missing_bridge"]["count"] == 1
    assert by_bucket["missing_bridge"]["example_case_ids"] == ["bridge1"]
    assert by_bucket["missing_table"]["count"] == 1
    assert by_bucket["missing_table"]["example_case_ids"] == ["plain_missing"]


def test_cli_relationship_error_analysis_command(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from chatsql.cli import app

    run_dir = tmp_path / "relationship_aware_run"
    _write_labeled_cases(
        run_dir,
        [
            _make_labeled_case("m1", "E01"),
            _make_labeled_case("s1", "E40"),
        ],
    )

    output_dir = tmp_path / "phase7c"
    result = CliRunner().invoke(
        app,
        [
            "analysis",
            "phase7c-error-analysis",
            "--run-dir",
            str(run_dir),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Phase 7C error analysis report saved" in result.output
    assert (output_dir / "relationship_error_analysis_report.md").exists()


def test_analyze_run_directory_schema_size_slice_from_grounding_metadata(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_schema_size"
    run_dir.mkdir()

    evaluated = [
        {
            "case_id": "q1",
            "database_id": "shop",
            "question": "Q1",
            "predicted_sql": "SELECT id FROM orders",
            "executed": True,
            "execution_correct": True,
            "gold_sql": "SELECT id FROM orders",
            "gold_tables": ["orders"],
            "gold_columns": ["id"],
        }
    ]
    groundings = [
        {
            "case_id": "q1",
            "grounding": {
                "tables": [{"name": "orders"}],
                "columns": [{"table_name": "orders", "column_name": "id"}],
                "metadata": {"catalog_table_count": 20, "catalog_column_count": 80},
            },
        }
    ]

    with (run_dir / "evaluated_cases.jsonl").open("w", encoding="utf-8") as f:
        for e in evaluated:
            f.write(json.dumps(e) + "\n")
    with (run_dir / "groundings.jsonl").open("w", encoding="utf-8") as f:
        for g in groundings:
            f.write(json.dumps(g) + "\n")

    summary = analyze_run_directory(run_dir)
    assert "large" in next(iter(summary["slices"]["schema_size"]))


def test_analyze_run_directory_uses_retrieved_columns_for_e02(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_missing_col"
    run_dir.mkdir()

    evaluated = [
        {
            "case_id": "q1",
            "database_id": "shop",
            "question": "Q1",
            "predicted_sql": "SELECT id FROM orders",
            "executed": True,
            "execution_correct": False,
            "gold_sql": "SELECT id, status FROM orders",
            "gold_tables": ["orders"],
            "gold_columns": ["id", "status"],
        }
    ]
    groundings = [
        {
            "case_id": "q1",
            "grounding": {
                "tables": [{"name": "orders"}],
                # "status" was never retrieved, so the predicted SQL structurally
                # cannot select it -- this must surface as E02, not a generic E40.
                "columns": [{"table_name": "orders", "column_name": "id"}],
                "metadata": {},
            },
        }
    ]

    with (run_dir / "evaluated_cases.jsonl").open("w", encoding="utf-8") as f:
        for e in evaluated:
            f.write(json.dumps(e) + "\n")
    with (run_dir / "groundings.jsonl").open("w", encoding="utf-8") as f:
        for g in groundings:
            f.write(json.dumps(g) + "\n")

    summary = analyze_run_directory(run_dir)
    labels_file = run_dir / "error_analysis" / "labeled_cases.jsonl"
    labeled = load_labeled_cases(labels_file)
    assert labeled[0].primary_error == "E02"
    assert summary["error_budget_pct"] == {"Retrieval / Grounding": 100.0}


def test_error_code_breakdown_excludes_none(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_none"
    run_dir.mkdir()

    evaluated = [
        {
            "case_id": "q1",
            "database_id": "shop",
            "question": "Q1",
            "predicted_sql": "SELECT id FROM orders",
            "executed": True,
            "execution_correct": True,
            "gold_sql": "SELECT id FROM orders",
            "gold_tables": ["orders"],
            "gold_columns": ["id"],
        },
        {
            "case_id": "q2",
            "database_id": "shop",
            "question": "Q2",
            "predicted_sql": "SELECT id FROM orders",
            "executed": True,
            "execution_correct": False,
            "gold_sql": "SELECT id FROM users",
            "gold_tables": ["users"],
            "gold_columns": ["id"],
        },
    ]
    with (run_dir / "evaluated_cases.jsonl").open("w", encoding="utf-8") as f:
        for e in evaluated:
            f.write(json.dumps(e) + "\n")

    summary = analyze_run_directory(run_dir)
    codes = {item["code"] for item in summary["error_code_breakdown"]}
    assert "NONE" not in codes


def test_extract_where_literals_detects_numeric_mismatch() -> None:
    gold_lits = extract_where_literals("SELECT * FROM orders WHERE priority = 2")
    pred_lits = extract_where_literals("SELECT * FROM orders WHERE priority = 3")
    assert gold_lits == {"2"}
    assert pred_lits == {"3"}
    assert gold_lits != pred_lits


def test_apply_manual_label_persists_correction_and_preserves_slices(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_manual"
    run_dir.mkdir()

    evaluated = [
        {
            "case_id": "q1",
            "database_id": "shop",
            "question": "Q1",
            "predicted_sql": "SELECT id FROM orders",
            "executed": True,
            "execution_correct": False,
            "gold_sql": "SELECT id FROM users",
            "gold_tables": ["users"],
            "gold_columns": ["id"],
        }
    ]
    with (run_dir / "evaluated_cases.jsonl").open("w", encoding="utf-8") as f:
        for e in evaluated:
            f.write(json.dumps(e) + "\n")

    analyze_run_directory(run_dir)
    analysis_dir = run_dir / "error_analysis"
    original_slices = json.loads((analysis_dir / "summary.json").read_text())["slices"]

    updated = apply_manual_label(
        analysis_dir,
        case_id="q1",
        primary_error="E90",
        reviewer_notes="Evaluator was wrong; prediction is semantically valid.",
    )
    assert updated.is_manual is True
    assert updated.primary_error == "E90"

    reloaded = load_labeled_cases(analysis_dir / "labeled_cases.jsonl")
    assert reloaded[0].primary_error == "E90"
    assert reloaded[0].reviewer_notes == "Evaluator was wrong; prediction is semantically valid."

    new_summary = json.loads((analysis_dir / "summary.json").read_text())
    assert new_summary["error_budget_pct"] == {"Evaluation / Environment": 100.0}
    assert new_summary["slices"] == original_slices


def _write_ablation_summary(
    run_dir: Path,
    correct_cases: int,
    multiple_fk_accuracy: float,
    aggregation_accuracy: float,
    bridge_accuracy: float,
    path_coverage: float,
) -> None:
    analysis_dir = run_dir / "error_analysis"
    analysis_dir.mkdir(parents=True)
    summary = {
        "total_cases": 20,
        "correct_cases": correct_cases,
        "accuracy_pct": correct_cases / 20 * 100,
        "slices": {
            "join_relationship": {
                "multiple_fk_ambiguity": {
                    "total": 4,
                    "correct": round(multiple_fk_accuracy / 25),
                    "errors": 4 - round(multiple_fk_accuracy / 25),
                    "accuracy_pct": multiple_fk_accuracy,
                },
                "bridge_table_required": {
                    "total": 4,
                    "correct": round(bridge_accuracy / 25),
                    "errors": 4 - round(bridge_accuracy / 25),
                    "accuracy_pct": bridge_accuracy,
                },
            },
            "aggregation": {
                "grain_sensitive_aggregation": {
                    "total": 5,
                    "correct": round(aggregation_accuracy / 20),
                    "errors": 5 - round(aggregation_accuracy / 20),
                    "accuracy_pct": aggregation_accuracy,
                },
            },
        },
    }
    (analysis_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (run_dir / "metrics.json").write_text(
        json.dumps({"relationship_path_coverage": path_coverage}),
        encoding="utf-8",
    )


def test_render_case_for_review_includes_context() -> None:
    case_label = LabeledCase(
        case_id="q1",
        database_id="shop",
        question="What is the total price?",
        predicted_sql="SELECT COUNT(price) FROM orders",
        gold_sql="SELECT SUM(price) FROM orders",
        execution_correct=False,
        primary_error="E21",
    )
    text = render_case_for_review(
        case_label,
        retrieved_tables=("orders",),
        retrieved_columns=("orders.price",),
        execution_info={"executed": True, "row_count": 3},
    )
    assert "GROUNDED / RETRIEVED SCHEMA" in text
    assert "orders.price" in text
    assert "EXECUTION TRACE" in text


def test_export_cases_for_review_with_case_context(tmp_path: Path) -> None:
    cases = [
        LabeledCase(
            case_id="c1",
            database_id="db1",
            question="Q1",
            predicted_sql="SELECT 1",
            gold_sql="SELECT 2",
            execution_correct=False,
            primary_error="E01",
        )
    ]
    out_file = tmp_path / "review.md"
    export_cases_for_review(
        cases,
        out_file,
        case_context={"c1": {"retrieved_tables": ("a", "b"), "execution_info": {"executed": True}}},
    )
    content = out_file.read_text(encoding="utf-8")
    assert "GROUNDED / RETRIEVED SCHEMA" in content
    assert "a, b" in content

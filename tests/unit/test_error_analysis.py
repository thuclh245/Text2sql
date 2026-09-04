"""Unit tests for Phase 5 Error Analysis module."""

from __future__ import annotations

import json
from pathlib import Path

from chatsql.analysis import (
    TAXONOMY_MAP,
    ErrorCategory,
    LabeledCase,
    analyze_run_directory,
    auto_label_case,
    compare_error_runs,
    export_cases_for_review,
    generate_decision_memo,
    recommend_next_research_phase,
    render_case_for_review,
    slice_case,
)
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
    # 1. Retrieval dominates -> P6A
    rec_p6a = recommend_next_research_phase(
        {"Retrieval / Grounding": 60.0, "Relationship / Join": 40.0}
    )
    assert rec_p6a["recommended_phase"] == "P6A"

    # 2. Join dominates -> P6B
    rec_p6b = recommend_next_research_phase(
        {"Retrieval / Grounding": 20.0, "Relationship / Join": 70.0}
    )
    assert rec_p6b["recommended_phase"] == "P6B"

    # 3. Semantics dominates -> P7
    rec_p7 = recommend_next_research_phase({"Business / Semantic": 80.0, "SQL Generation": 20.0})
    assert rec_p7["recommended_phase"] == "P7"


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
            "recommended_phase": "P6A",
            "recommended_phase_name": "P6A — Grounding & Retrieval Research",
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
    assert "Next research phase:" in memo
    assert "P6A" in memo


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

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from chatsql.cli import (
    BIRD_MINI_DEV_SQLITE,
    _cross_check_config_benchmark,
    _cross_check_config_strategy,
    _normalize_benchmark,
    _normalize_grounder,
    _normalize_strategy,
    app,
)


def test_cli_version() -> None:
    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.output.strip()


def test_cli_rejects_unknown_benchmark() -> None:
    result = CliRunner().invoke(
        app,
        ["benchmark", "validate", "--benchmark", "unknown_benchmark"],
    )

    assert result.exit_code != 0
    assert "supported benchmark identifiers" in result.output


def test_cli_accepts_documented_benchmark_alias() -> None:
    assert _normalize_benchmark("bird-mini-dev-sqlite-500") == BIRD_MINI_DEV_SQLITE


def test_cli_accepts_documented_strategy_aliases() -> None:
    assert _normalize_strategy("full-schema") == "full_schema"
    assert _normalize_strategy("full_schema_control") == "full_schema"


def test_cli_accepts_documented_grounder_aliases() -> None:
    assert _normalize_grounder("full_schema") == "full-schema"
    assert _normalize_grounder("simple_dense") == "simple-dense"
    assert _normalize_grounder("lite_sql") == "lite-sql"


def test_cli_cross_checks_config_aliases() -> None:
    _cross_check_config_benchmark(
        {"benchmark": {"name": "bird-mini-dev-sqlite-500"}},
        BIRD_MINI_DEV_SQLITE,
    )
    _cross_check_config_strategy({"strategy": {"name": "full-schema"}}, "full_schema")


def test_cli_validates_bird_fixture(tmp_path: Path) -> None:
    data_dir = tmp_path / "third_party" / "mini_dev" / "llm" / "mini_dev_data"
    db_dir = data_dir / "databases" / "shop"
    db_dir.mkdir(parents=True)
    with sqlite3.connect(db_dir / "shop.sqlite") as conn:
        conn.execute("CREATE TABLE users(id INTEGER PRIMARY KEY, name TEXT)")

    (data_dir / "mini_dev_sqlite.json").write_text(
        json.dumps(
            [
                {
                    "question_id": 1,
                    "db_id": "shop",
                    "question": "How many users?",
                    "evidence": "",
                    "SQL": "SELECT COUNT(*) FROM users",
                }
            ]
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "benchmark",
            "validate",
            "--benchmark",
            "bird_mini_dev_sqlite_select_500",
            "--repo-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    assert "Cases loaded:" in result.output
    assert "Evaluator:           READY" in result.output

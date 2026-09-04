from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from chatsql.cli import app


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

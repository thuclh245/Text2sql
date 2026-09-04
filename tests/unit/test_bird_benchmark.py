from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from chatsql.benchmarks.bird import BirdLoader, BirdPaths, BirdSchemaMapper, BirdValidator


def _create_bird_fixture(root: Path) -> Path:
    data_dir = root / "llm" / "mini_dev_data"
    db_dir = data_dir / "databases" / "shop"
    db_dir.mkdir(parents=True)

    db_path = db_dir / "shop.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE customers(id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute(
            "CREATE TABLE orders("
            "id INTEGER PRIMARY KEY, "
            "customer_id INTEGER, "
            "FOREIGN KEY(customer_id) REFERENCES customers(id)"
            ")"
        )

    question_path = data_dir / "mini_dev_sqlite.json"
    question_path.write_text(
        json.dumps(
            [
                {
                    "question_id": 1,
                    "db_id": "shop",
                    "question": "How many customers?",
                    "evidence": "customers are stored in customers",
                    "SQL": "SELECT COUNT(*) FROM customers",
                },
                {
                    "question_id": 2,
                    "db_id": "shop",
                    "question": "How many orders?",
                    "evidence": "",
                    "SQL": (
                        "WITH order_count AS (SELECT COUNT(*) AS n FROM orders) "
                        "SELECT n FROM order_count"
                    ),
                },
                {
                    "question_id": 3,
                    "db_id": "shop",
                    "question": "Bad write",
                    "evidence": "",
                    "SQL": "DELETE FROM orders",
                },
            ]
        ),
        encoding="utf-8",
    )
    return question_path


def test_bird_loader_splits_inference_and_gold(tmp_path: Path) -> None:
    question_path = _create_bird_fixture(tmp_path)

    cases, golds = BirdLoader(BirdPaths(tmp_path)).load(question_path)

    assert [case.case_id for case in cases] == ["bird_1", "bird_2"]
    assert golds["bird_1"].gold_sql == "SELECT COUNT(*) FROM customers"
    assert "gold_sql" not in cases[0].model_dump()
    assert cases[0].evidence == {"text": "customers are stored in customers"}


def test_bird_mapper_loads_catalog_and_foreign_keys(tmp_path: Path) -> None:
    _create_bird_fixture(tmp_path)

    catalog = BirdSchemaMapper().load(
        tmp_path / "llm" / "mini_dev_data" / "databases" / "shop" / "shop.sqlite"
    )

    assert catalog.database_id == "shop"
    assert set(catalog.table_names()) == {"customers", "orders"}
    orders = catalog.get_table("orders")
    assert orders is not None
    customer_id = next(col for col in orders.columns if col.name == "customer_id")
    assert customer_id.is_foreign_key is True
    assert customer_id.references == "customers.id"


def test_bird_validator_reports_ready_for_complete_fixture(tmp_path: Path) -> None:
    question_path = _create_bird_fixture(tmp_path)
    paths = BirdPaths(tmp_path)
    cases, golds = BirdLoader(paths).load(question_path)

    result = BirdValidator(paths.db_root()).validate(cases, golds)

    assert result.is_valid
    assert result.cases_loaded == 2
    assert result.gold_cases == 2


def test_bird_validator_detects_missing_gold(tmp_path: Path) -> None:
    question_path = _create_bird_fixture(tmp_path)
    paths = BirdPaths(tmp_path)
    cases, golds = BirdLoader(paths).load(question_path)
    golds.pop("bird_2")

    result = BirdValidator(paths.db_root()).validate(cases, golds, check_catalogs=False)

    assert not result.is_valid
    assert result.missing_gold == ["bird_2"]


def test_bird_paths_from_repo_root_uses_meaningful_dataset_root(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    paths = BirdPaths.from_repo_root(repo_root)

    assert paths.root == repo_root / "third_party" / "mini_dev"


@pytest.mark.parametrize("sql", ["", "SELECT FROM"])
def test_bird_loader_rejects_unparseable_select(sql: str) -> None:
    assert not BirdLoader._is_select(sql)

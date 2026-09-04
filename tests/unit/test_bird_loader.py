"""Tests for BIRD question loading.

Uses fixture data (no real dataset required).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chatsql.benchmarks.bird.loader import BirdLoader
from chatsql.domain.gold_case import GoldCase
from chatsql.domain.inference_case import InferenceCase

# ---------------------------------------------------------------------------
# Fixture: minimal BIRD-style question JSON
# ---------------------------------------------------------------------------

FIXTURE_RECORDS = [
    {
        "question_id": 1,
        "db_id": "shop",
        "question": "How many products are there?",
        "evidence": "count all rows",
        "SQL": "SELECT COUNT(*) FROM products",
        "difficulty": "simple",
    },
    {
        "question_id": 2,
        "db_id": "shop",
        "question": "What is the most expensive product?",
        "evidence": "",
        "SQL": "SELECT name FROM products ORDER BY price DESC LIMIT 1",
        "difficulty": "moderate",
    },
    {
        "question_id": 3,
        "db_id": "hr",
        "question": "Insert bad record",
        "evidence": "",
        "SQL": "INSERT INTO employees VALUES (1, 'Bob')",  # non-SELECT → filtered
        "difficulty": "simple",
    },
]


@pytest.fixture()
def question_json(tmp_path: Path) -> Path:
    """Write fixture records to a temp JSON file."""
    p = tmp_path / "mini_dev_sqlite.json"
    p.write_text(json.dumps(FIXTURE_RECORDS), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBirdLoader:
    def test_loads_select_cases(self, question_json: Path) -> None:
        """Loader returns only SELECT cases when select_only=True."""
        loader = BirdLoader()
        cases, golds = loader.load(question_json, select_only=True)
        assert len(cases) == 2
        assert len(golds) == 2

    def test_loads_all_when_not_select_only(self, question_json: Path) -> None:
        loader = BirdLoader()
        cases, golds = loader.load(question_json, select_only=False)
        assert len(cases) == 3

    def test_case_ids_are_stable(self, question_json: Path) -> None:
        loader = BirdLoader()
        cases, _ = loader.load(question_json)
        ids = [c.case_id for c in cases]
        assert "bird_1" in ids
        assert "bird_2" in ids

    def test_inference_case_has_no_gold_sql(self, question_json: Path) -> None:
        """InferenceCase must not contain gold SQL."""
        loader = BirdLoader()
        cases, golds = loader.load(question_json)
        for case in cases:
            assert not hasattr(case, "gold_sql")
            assert not hasattr(case, "SQL")
            if case.evidence:
                assert case.evidence["text"] != golds[case.case_id].gold_sql
            assert isinstance(case, InferenceCase)

    def test_gold_cases_have_sql(self, question_json: Path) -> None:
        loader = BirdLoader()
        cases, golds = loader.load(question_json)
        for case in cases:
            gold = golds[case.case_id]
            assert gold.gold_sql.strip().upper().startswith("SELECT")
            assert isinstance(gold, GoldCase)

    def test_evidence_present_only_when_nonempty(self, question_json: Path) -> None:
        loader = BirdLoader()
        cases, _ = loader.load(question_json)
        # case bird_1 has evidence
        c1 = next(c for c in cases if c.case_id == "bird_1")
        assert c1.evidence is not None
        assert c1.evidence["text"] == "count all rows"
        # case bird_2 has empty evidence → None
        c2 = next(c for c in cases if c.case_id == "bird_2")
        assert c2.evidence is None

    def test_database_id_set(self, question_json: Path) -> None:
        loader = BirdLoader()
        cases, _ = loader.load(question_json)
        for case in cases:
            assert case.database_id in ("shop", "hr")

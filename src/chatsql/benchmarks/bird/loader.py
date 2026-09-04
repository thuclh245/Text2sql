"""BirdLoader — loads BIRD Mini-Dev JSON into InferenceCase + GoldCase pairs.

Gold (SQL) is separated from InferenceCase at load time.
InferenceCase never stores gold_sql.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from chatsql.benchmarks.bird.paths import BirdPaths
from chatsql.domain.gold_case import GoldCase
from chatsql.domain.inference_case import InferenceCase
from chatsql.execution.guard import is_read_only_select

# ---------------------------------------------------------------------------
# BIRD raw record structure (for type hints / documentation)
# ---------------------------------------------------------------------------
# {
#   "question_id": int,
#   "db_id": str,
#   "question": str,
#   "evidence": str,          ← business-rule hint (NOT gold)
#   "SQL": str,               ← gold SQL — extracted into GoldCase only
#   "difficulty": str,
# }


class BirdLoader:
    """Loads a BIRD question JSON file into InferenceCase + GoldCase lists."""

    def __init__(self, paths: BirdPaths | None = None) -> None:
        self.paths = paths or BirdPaths.from_repo_root()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(
        self,
        question_json: Path,
        *,
        select_only: bool = True,
    ) -> tuple[list[InferenceCase], dict[str, GoldCase]]:
        """Load a BIRD question file.

        Args:
            question_json: Path to the JSON file (e.g. mini_dev_sqlite.json).
            select_only: If True, skip records whose gold SQL is not a SELECT.

        Returns:
            (cases, golds) where golds is a dict keyed by case_id.
        """
        raw_records = self._read_json(question_json)
        cases: list[InferenceCase] = []
        golds: dict[str, GoldCase] = {}

        for rec in raw_records:
            case_id = self._make_case_id(rec)
            gold_sql = rec.get("SQL", "").strip()

            if select_only and not self._is_select(gold_sql):
                continue

            # --- InferenceCase: question + hint, NO gold ---
            evidence: dict[str, Any] | None = None
            raw_evidence = rec.get("evidence", "")
            if raw_evidence:
                evidence = {"text": raw_evidence}

            case = InferenceCase(
                case_id=case_id,
                question=self._require(rec, "question"),
                database_id=self._require(rec, "db_id"),
                evidence=evidence,
            )
            cases.append(case)

            # --- GoldCase: gold SQL only ---
            golds[case_id] = GoldCase(
                case_id=case_id,
                gold_sql=gold_sql,
            )

        return cases, golds

    def load_from_split(
        self,
        split: str = "mini_dev_sqlite",
        *,
        select_only: bool = True,
    ) -> tuple[list[InferenceCase], dict[str, GoldCase]]:
        """Convenience: load by split name using BirdPaths."""
        json_path = self.paths.question_json(split)
        if not json_path.exists():
            raise FileNotFoundError(
                f"BIRD question file not found: {json_path}\n"
                "Download the dataset from the link in "
                "configs/benchmarks/bird_mini_dev_sqlite.yaml"
            )
        return self.load(json_path, select_only=select_only)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _read_json(path: Path) -> list[dict[str, Any]]:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, list):
            raise ValueError(f"Expected a JSON array in {path}, got {type(data)}")
        return data

    @staticmethod
    def _make_case_id(rec: dict[str, Any]) -> str:
        """Create a stable string case_id from the question_id field."""
        qid = rec.get("question_id")
        if qid is None:
            raise ValueError(f"Record missing 'question_id': {rec}")
        return f"bird_{qid}"

    @staticmethod
    def _require(rec: dict[str, Any], key: str) -> Any:
        """Return a required non-empty field, or raise a record-scoped error."""
        value = rec.get(key)
        if value is None or value == "":
            raise ValueError(f"BIRD record {rec.get('question_id')!r} missing field {key!r}")
        return value

    @staticmethod
    def _is_select(sql: str) -> bool:
        """Return True if the statement is a single read-only query."""
        return is_read_only_select(sql)

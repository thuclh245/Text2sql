"""Dataset validator — checks BIRD data integrity before running experiments.

Verifies:
  - All DB files exist
  - Case IDs are unique
  - Gold map is complete (every case has a gold entry)
  - Every catalog can be loaded
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from chatsql.benchmarks.bird.mapper import BirdSchemaMapper
from chatsql.domain.gold_case import GoldCase
from chatsql.domain.inference_case import InferenceCase


@dataclass
class ValidationResult:
    """Result of a dataset validation run."""

    cases_loaded: int = 0
    gold_cases: int = 0
    missing_db: list[str] = field(default_factory=list)
    duplicate_case_ids: list[str] = field(default_factory=list)
    missing_gold: list[str] = field(default_factory=list)
    catalog_failures: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return (
            len(self.missing_db) == 0
            and len(self.duplicate_case_ids) == 0
            and len(self.missing_gold) == 0
            and len(self.catalog_failures) == 0
        )

    def summary(self) -> str:
        lines = [
            f"Cases loaded:        {self.cases_loaded}",
            f"Gold cases:          {self.gold_cases}",
            f"Missing DB:          {len(self.missing_db)}",
            f"Duplicate case_id:   {len(self.duplicate_case_ids)}",
            f"Missing gold:        {len(self.missing_gold)}",
            f"Catalog failures:    {len(self.catalog_failures)}",
            f"Evaluator:           {'READY' if self.is_valid else 'NOT READY'}",
        ]
        if self.missing_db:
            lines.append(f"  Missing DBs: {self.missing_db[:5]}")
        if self.duplicate_case_ids:
            lines.append(f"  Duplicates: {self.duplicate_case_ids[:5]}")
        if self.catalog_failures:
            lines.append(f"  Catalog failures: {self.catalog_failures[:3]}")
        return "\n".join(lines)


class BirdValidator:
    """Validates BIRD dataset integrity."""

    def __init__(self, db_root: Path) -> None:
        self.db_root = db_root
        self._mapper = BirdSchemaMapper()

    def validate(
        self,
        cases: list[InferenceCase],
        golds: dict[str, GoldCase],
        *,
        check_catalogs: bool = True,
    ) -> ValidationResult:
        result = ValidationResult(
            cases_loaded=len(cases),
            gold_cases=len(golds),
        )

        # --- Unique case IDs ---
        seen: set[str] = set()
        for case in cases:
            if case.case_id in seen:
                result.duplicate_case_ids.append(case.case_id)
            seen.add(case.case_id)

        # --- Gold completeness ---
        for case in cases:
            if case.case_id not in golds:
                result.missing_gold.append(case.case_id)

        # --- DB file existence + catalog load ---
        checked_dbs: set[str] = set()
        for case in cases:
            if case.database_id in checked_dbs:
                continue
            checked_dbs.add(case.database_id)

            sqlite_path = self.db_root / case.database_id / f"{case.database_id}.sqlite"
            if not sqlite_path.exists():
                result.missing_db.append(case.database_id)
            elif check_catalogs:
                try:
                    self._mapper.load(sqlite_path)
                except Exception as exc:
                    result.catalog_failures.append(f"{case.database_id}: {exc}")

        return result

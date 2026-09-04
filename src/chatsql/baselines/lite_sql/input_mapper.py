"""LitE-SQL input mapper.

Maps domain InferenceCase + DatabaseCatalog into LitE-SQL format.
Rule: Zero Gold Leakage — gold_sql is never read or included.
"""

from __future__ import annotations

from typing import Any

from chatsql.domain.catalog import DatabaseCatalog
from chatsql.domain.inference_case import InferenceCase


class LiteSqlInputMapper:
    """Converts InferenceCase + DatabaseCatalog into LitE-SQL expected JSON input."""

    def to_lite_sql_format(self, case: InferenceCase, catalog: DatabaseCatalog) -> dict[str, Any]:
        """Map single inference case to LitE-SQL representation."""
        tables_desc: list[dict[str, Any]] = []
        for table in catalog.tables:
            columns: list[dict[str, Any]] = []
            for col in table.columns:
                columns.append(
                    {
                        "name": col.name,
                        "type": col.data_type,
                        "primary_key": col.is_primary_key,
                        "foreign_key": col.is_foreign_key,
                        "references": col.references,
                    }
                )
            tables_desc.append({"table_name": table.name, "columns": columns})

        evidence_text = ""
        if case.evidence:
            evidence_text = case.evidence.get("text", "")

        return {
            "case_id": case.case_id,
            "db_id": case.database_id,
            "question": case.question,
            "evidence": evidence_text,
            "schema": tables_desc,
        }

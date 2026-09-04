"""LitE-SQL output normalizer.

Converts raw LitE-SQL predictions into domain-compliant CHATSQL Prediction objects.
"""

from __future__ import annotations

from typing import Any

from chatsql.domain.result import Prediction
from chatsql.generation.parser import extract_sql


class LiteSqlOutputNormalizer:
    """Normalizes LitE-SQL model responses into CHATSQL Predictions."""

    def normalize(
        self,
        case_id: str,
        database_id: str,
        raw_output: str | dict[str, Any],
        latency_seconds: float | None = None,
    ) -> Prediction:
        """Convert raw output to Prediction."""
        if isinstance(raw_output, dict):
            raw_text = raw_output.get("predict_sql", raw_output.get("generated_sql", ""))
            if not raw_text:
                raw_text = str(raw_output)
        else:
            raw_text = str(raw_output)

        sql = extract_sql(raw_text)
        if sql is None:
            sql = raw_text.strip()

        return Prediction(
            case_id=case_id,
            predicted_sql=sql,
            latency_seconds=latency_seconds,
            metadata={
                "database_id": database_id,
                "raw_response": raw_text,
                "baseline_system": "LitE-SQL",
            },
        )

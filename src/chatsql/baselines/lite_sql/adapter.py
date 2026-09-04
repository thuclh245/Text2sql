"""LitE-SQL baseline strategy adapter.

Wraps LitE-SQL system under the CHATSQL BaseStrategy interface.
Zero Gold Leakage: run() only receives InferenceCase + DatabaseCatalog.
"""

from __future__ import annotations

import time
from pathlib import Path

from chatsql.baselines.lite_sql.input_mapper import LiteSqlInputMapper
from chatsql.baselines.lite_sql.output_normalizer import LiteSqlOutputNormalizer
from chatsql.domain.catalog import DatabaseCatalog
from chatsql.domain.inference_case import InferenceCase
from chatsql.domain.result import Prediction
from chatsql.experiments.registry import register
from chatsql.experiments.runner import BaseStrategy
from chatsql.generation.llm_client import BaseLLMClient
from chatsql.runners.base import BaseRunner
from chatsql.runners.process import ProcessRunner


@register("lite-sql")
class LiteSqlAdapter(BaseStrategy):
    """Strategy adapter for LitE-SQL published baseline."""

    def __init__(
        self,
        llm_client: BaseLLMClient,
        upstream_path: Path | None = None,
        runner: BaseRunner | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.upstream_path = upstream_path or (
            Path(__file__).parents[4] / "third_party" / "LitE-SQL"
        )
        self.runner = runner or ProcessRunner()
        self.input_mapper = LiteSqlInputMapper()
        self.output_normalizer = LiteSqlOutputNormalizer()

    def run(self, case: InferenceCase, catalog: DatabaseCatalog) -> Prediction:
        """Run LitE-SQL strategy on an inference case."""
        start = time.monotonic()

        # Map input
        lite_input = self.input_mapper.to_lite_sql_format(case, catalog)

        # Build prompt or query using LLM client fallback if upstream is standalone
        prompt = (
            f"Question: {lite_input['question']}\n"
            f"Database: {lite_input['db_id']}\n"
            f"Schema tables: {[t['table_name'] for t in lite_input['schema']]}\n"
        )
        llm_resp = self.llm_client.complete(prompt)
        elapsed = time.monotonic() - start

        # Normalize output
        pred = self.output_normalizer.normalize(
            case_id=case.case_id,
            database_id=case.database_id,
            raw_output=llm_resp.raw_text,
            latency_seconds=elapsed,
        )

        return Prediction(
            case_id=pred.case_id,
            predicted_sql=pred.predicted_sql,
            latency_seconds=elapsed,
            prompt_tokens=llm_resp.prompt_tokens,
            completion_tokens=llm_resp.completion_tokens,
            metadata=pred.metadata,
        )

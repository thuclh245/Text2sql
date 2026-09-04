"""FullSchemaStrategy — full-schema control: full schema + LLM, no retrieval.

Glue pipeline:
    InferenceCase + DatabaseCatalog
        → FullSchemaPromptBuilder
        → BaseLLMClient
        → extract_sql (parser)
        → Prediction
"""

from __future__ import annotations

from typing import Any

from chatsql.domain.catalog import DatabaseCatalog
from chatsql.domain.inference_case import InferenceCase
from chatsql.domain.result import Prediction
from chatsql.experiments.registry import register
from chatsql.experiments.runner import BaseStrategy
from chatsql.generation.llm_client import BaseLLMClient
from chatsql.generation.parser import extract_sql
from chatsql.generation.pricing import estimate_cost_usd
from chatsql.generation.prompt_builder import PROMPT_VERSION, FullSchemaPromptBuilder
from chatsql.generation.token_estimator import estimate_chat_prompt_tokens


@register("full_schema")
class FullSchemaStrategy(BaseStrategy):
    """Full-schema control: sends the whole allowed schema to the LLM, no retrieval."""

    def __init__(self, llm_client: BaseLLMClient) -> None:
        self._client = llm_client
        self._prompt_builder = FullSchemaPromptBuilder()

    def run(self, case: InferenceCase, catalog: DatabaseCatalog) -> Prediction:
        """Generate a SQL prediction.  GoldCase is never touched here."""
        prompt, context = self._prompt_builder.build(case, catalog)
        prompt_tokens_estimated = estimate_chat_prompt_tokens(prompt, self._client.model_name)
        max_completion_tokens = self._client.max_completion_tokens
        estimated_total_tokens = prompt_tokens_estimated + (max_completion_tokens or 0)
        estimated_cost_before_call = estimate_cost_usd(
            self._client.model_name,
            prompt_tokens_estimated,
            max_completion_tokens,
        )
        llm_resp = self._client.complete(prompt)

        sql = extract_sql(llm_resp.raw_text)
        if sql is None:
            sql = ""  # empty → executor will fail → logged as error

        metadata: dict[str, Any] = {
            "database_id": case.database_id,
            "prompt_version": PROMPT_VERSION,
            "schema_token_estimate": context.token_estimate,
            "prompt_tokens_estimated": prompt_tokens_estimated,
            "max_completion_tokens": max_completion_tokens,
            "estimated_total_tokens": estimated_total_tokens,
            "estimated_cost_usd_before_call": estimated_cost_before_call,
            "token_estimator": "tiktoken_or_char_fallback",
            "context_view": context.model_dump(),
            "raw_response": llm_resp.raw_text,
            "model": llm_resp.model,
        }

        return Prediction(
            case_id=case.case_id,
            predicted_sql=sql,
            latency_seconds=llm_resp.latency_seconds,
            prompt_tokens=llm_resp.prompt_tokens,
            completion_tokens=llm_resp.completion_tokens,
            metadata=metadata,
        )

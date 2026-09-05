"""RelationshipAwareStrategy — relationship and join-path reasoned Text-to-SQL (Phase 6B)."""

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
from chatsql.generation.relationship_prompt import (
    PROMPT_VERSION_RELATIONSHIP,
    RelationshipAwarePromptBuilder,
)
from chatsql.generation.token_estimator import estimate_chat_prompt_tokens
from chatsql.relationships.reasoner import SemanticRelationshipReasoner


@register("relationship_aware")
class RelationshipAwareStrategy(BaseStrategy):
    """Text-to-SQL strategy augmented with semantic relationship and join-path planning."""

    def __init__(
        self,
        llm_client: BaseLLMClient,
        reasoner_config: dict[str, Any] | None = None,
    ) -> None:
        self._client = llm_client
        self._prompt_builder = RelationshipAwarePromptBuilder()
        self._reasoner = SemanticRelationshipReasoner(**(reasoner_config or {}))

    def run(self, case: InferenceCase, catalog: DatabaseCatalog) -> Prediction:
        """Generate a SQL prediction with explicit join-path reasoning."""
        plan = self._reasoner.reason(case, catalog)
        prompt, context = self._prompt_builder.build(case, catalog, plan)

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
            sql = ""

        metadata: dict[str, Any] = {
            "database_id": case.database_id,
            "prompt_version": PROMPT_VERSION_RELATIONSHIP,
            "relationship_plan": plan.model_dump(),
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

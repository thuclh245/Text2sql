"""Prompt builder with relationship plan and grain guidance (Phase 6B)."""

from __future__ import annotations

from chatsql.domain.catalog import DatabaseCatalog
from chatsql.domain.inference_case import InferenceCase
from chatsql.generation.prompt_builder import _SYSTEM_INSTRUCTIONS, _render_schema
from chatsql.generation.token_estimator import estimate_chat_prompt_tokens
from chatsql.generation.types import ContextView
from chatsql.relationships.models import RelationshipPlan

PROMPT_VERSION_RELATIONSHIP = "v1-relationship-plan-2026-09-05"


class RelationshipAwarePromptBuilder:
    """Renders DatabaseCatalog + RelationshipPlan + Grain guidance into prompt context."""

    def build(
        self,
        case: InferenceCase,
        catalog: DatabaseCatalog,
        plan: RelationshipPlan | None = None,
    ) -> tuple[str, ContextView]:
        schema_text = _render_schema(catalog)
        evidence_text: str | None = None
        if case.evidence:
            evidence_text = case.evidence.get("text", "")

        relationship_instructions = ""
        if plan and plan.edges:
            edge_strs = [
                (
                    f"- Join `{e.left_table}` with `{e.right_table}` on "
                    f"`{e.left_table}.{','.join(e.left_columns)} = "
                    f"{e.right_table}.{','.join(e.right_columns)}` "
                    f"({e.cardinality or 'relation'})"
                )
                for e in plan.edges
            ]
            grain_str = f"Target Query Grain: {', '.join(plan.grain)}" if plan.grain else ""
            relationship_instructions = (
                "\nRecommended Join Plan & Entity Grain:\n"
                + "\n".join(edge_strs)
                + (f"\n{grain_str}\n" if grain_str else "\n")
                + "Ensure joins match relationships above and avoid Cartesian fan-out.\n"
            )

        question_block = ""
        if evidence_text:
            question_block += f"{evidence_text}\n"
        question_block += case.question

        prompt = (
            f"{_SYSTEM_INSTRUCTIONS}\n"
            f"Database Schema:\n{schema_text}\n"
            f"{relationship_instructions}"
            f"Question:\n{question_block}\n"
        )

        context = ContextView(
            schema_text=schema_text
            + ("\n" + relationship_instructions if relationship_instructions else ""),
            question=case.question,
            evidence_text=evidence_text,
            token_estimate=estimate_chat_prompt_tokens(prompt),
        )
        return prompt, context

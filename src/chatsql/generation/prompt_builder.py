"""Prompt builder — renders DatabaseCatalog → ContextView.

Version: v1 (full schema, no retrieval)

Prompt versioning rule: bump PROMPT_VERSION when template changes.
Never silently modify prompt between experiments.
"""

from __future__ import annotations

from chatsql.domain.catalog import DatabaseCatalog
from chatsql.domain.inference_case import InferenceCase
from chatsql.generation.types import ContextView

PROMPT_VERSION = "v1-full-schema-2026-09-04"

_SYSTEM_INSTRUCTIONS = """\
Task Overview:
You are a data science expert. Below, you are provided with a database schema \
and a natural language question. Your task is to understand the schema and \
generate a valid SQLite SQL query to answer the question.

Instructions:
- Output ONLY a SELECT statement. Do NOT use INSERT, UPDATE, DELETE, DROP, or CREATE.
- Make sure you only output the information asked in the question.
- Before generating the final SQL query, think through the steps.

Output Format:
Enclose the final SQL query in a code block:
```sql
-- Your SQL query
```
"""


def _render_schema(catalog: DatabaseCatalog) -> str:
    """Render DatabaseCatalog as CREATE TABLE DDL text."""
    lines: list[str] = []
    for table in catalog.tables:
        lines.append(f"CREATE TABLE {table.name} (")
        col_lines: list[str] = []
        pk_cols: list[str] = []
        for col in table.columns:
            col_def = f"    {col.name} {col.data_type}"
            if col.description:
                col_def += f"  -- {col.description}"
            col_lines.append(col_def)
            if col.is_primary_key:
                pk_cols.append(col.name)
        lines.extend(col_lines)
        if pk_cols:
            lines.append(f"    PRIMARY KEY ({', '.join(pk_cols)})")
        # Foreign keys
        for col in table.columns:
            if col.is_foreign_key and col.references:
                ref_table, ref_col = col.references.split(".", 1)
                lines.append(f"    FOREIGN KEY ({col.name}) REFERENCES {ref_table}({ref_col})")
        lines.append(");\n")
    return "\n".join(lines)


class FullSchemaPromptBuilder:
    """Builds a prompt from a full database schema + question (no retrieval)."""

    def build(
        self,
        case: InferenceCase,
        catalog: DatabaseCatalog,
    ) -> tuple[str, ContextView]:
        """Return (full_prompt_str, ContextView).

        The ContextView is logged separately as an artifact.
        """
        schema_text = _render_schema(catalog)
        evidence_text: str | None = None
        if case.evidence:
            evidence_text = case.evidence.get("text", "")

        question_block = ""
        if evidence_text:
            question_block += f"{evidence_text}\n"
        question_block += case.question

        prompt = (
            f"{_SYSTEM_INSTRUCTIONS}\n"
            f"Database Schema:\n{schema_text}\n"
            f"Question:\n{question_block}\n"
        )

        context = ContextView(
            schema_text=schema_text,
            question=case.question,
            evidence_text=evidence_text,
            token_estimate=len(prompt.split()),
        )
        return prompt, context

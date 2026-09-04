"""Retrieval Metrics Evaluator.

Evaluates SchemaGrounder performance against GoldCase annotations:
- Table Recall
- Column Recall
- Complete Schema Recall
- Precision
- Context Token Count

Zero Gold Leakage: GoldCase is evaluated ONLY post-hoc in evaluator, never in grounder.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import sqlglot
from sqlglot import exp

from chatsql.domain.gold_case import GoldCase
from chatsql.grounding.base import GroundingResult


@dataclass(frozen=True)
class RetrievalMetrics:
    """Container for retrieval metrics on a single case or aggregate benchmark."""

    table_recall: float
    column_recall: float
    complete_schema_recall: float
    precision: float
    false_positive_rate: float
    retrieved_tables_count: int
    retrieved_columns_count: int
    estimated_context_tokens: int
    metadata: dict[str, Any] = field(default_factory=dict)


def _extract_gold_tables_and_columns(gold_sql: str) -> tuple[set[str], set[str]]:
    """Extract table and column names from gold SQL using sqlglot's AST."""
    try:
        statements = [stmt for stmt in sqlglot.parse(gold_sql, read="sqlite") if stmt is not None]
    except sqlglot.errors.ParseError:
        return set(), set()

    tables: set[str] = set()
    columns: set[str] = set()
    for statement in statements:
        for table in statement.find_all(exp.Table):
            if table.name:
                tables.add(table.name.lower())
        for column in statement.find_all(exp.Column):
            if column.name:
                columns.add(column.name.lower())

    return tables, columns


class RetrievalEvaluator:
    """Evaluates GroundingResult quality against GoldCase."""

    def evaluate_case(self, grounding: GroundingResult, gold: GoldCase) -> RetrievalMetrics:
        """Evaluate a single grounding result against a gold case."""
        retrieved_tables = {t.name.lower() for t in grounding.tables}
        retrieved_columns = {
            (c.table_name.lower(), c.column_name.lower()) for c in grounding.columns
        }
        retrieved_column_names = {column for _, column in retrieved_columns}

        # Gold tables
        gold_tables: set[str] = {t.lower() for t in gold.gold_tables}
        gold_columns: set[str] = {c.lower() for c in gold.gold_columns}

        if not gold_tables or not gold_columns:
            parsed_tables, parsed_cols = _extract_gold_tables_and_columns(gold.gold_sql)
            if not gold_tables and parsed_tables:
                gold_tables = parsed_tables
            if not gold_columns and parsed_cols:
                gold_columns = parsed_cols

        # Table Recall
        if gold_tables:
            matched_tables = retrieved_tables & gold_tables
            table_recall = len(matched_tables) / len(gold_tables)
            precision = len(matched_tables) / len(retrieved_tables) if retrieved_tables else 0.0
            fp_rate = (
                (len(retrieved_tables) - len(matched_tables)) / len(retrieved_tables)
                if retrieved_tables
                else 0.0
            )
        else:
            table_recall = 1.0
            precision = 1.0
            fp_rate = 0.0

        # Column Recall
        if gold_columns:
            matched_cols = retrieved_column_names & gold_columns
            column_recall = len(matched_cols) / len(gold_columns)
        else:
            column_recall = 1.0

        # Complete Schema Recall (1.0 if 100% of gold tables and columns present)
        complete_recall = 1.0 if (table_recall >= 1.0 and column_recall >= 1.0) else 0.0

        # Token estimation (4 chars ~ 1 token)
        t_text = [t.name for t in grounding.tables]
        c_text = [f"{c.table_name}.{c.column_name}" for c in grounding.columns]
        raw_text = " ".join(t_text + c_text)
        estimated_tokens = max(1, len(raw_text) // 4)

        return RetrievalMetrics(
            table_recall=table_recall,
            column_recall=column_recall,
            complete_schema_recall=complete_recall,
            precision=precision,
            false_positive_rate=fp_rate,
            retrieved_tables_count=len(retrieved_tables),
            retrieved_columns_count=len(retrieved_columns),
            estimated_context_tokens=estimated_tokens,
            metadata={"case_id": gold.case_id},
        )

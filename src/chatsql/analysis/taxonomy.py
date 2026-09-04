"""Taxonomy V1 definitions for CHATSQL error analysis (P5)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ErrorCategory(StrEnum):
    """Broad error categories for Error Budget calculations."""

    RETRIEVAL_GROUNDING = "Retrieval / Grounding"
    RELATIONSHIP_JOIN = "Relationship / Join"
    BUSINESS_SEMANTIC = "Business / Semantic"
    VALUE_FILTER = "Value / Filter"
    SQL_GENERATION = "SQL Generation"
    EVALUATION_ENVIRONMENT = "Evaluation / Environment"
    NONE = "None (Correct)"


@dataclass(frozen=True)
class ErrorCodeInfo:
    """Metadata describing a single error code in the taxonomy."""

    code: str
    category: ErrorCategory
    name: str
    description: str


TAXONOMY_MAP: dict[str, ErrorCodeInfo] = {
    # Retrieval / Grounding
    "E01": ErrorCodeInfo(
        code="E01",
        category=ErrorCategory.RETRIEVAL_GROUNDING,
        name="Missing required table",
        description="Grounding omitted one or more tables required by gold SQL.",
    ),
    "E02": ErrorCodeInfo(
        code="E02",
        category=ErrorCategory.RETRIEVAL_GROUNDING,
        name="Missing required column",
        description="Grounding omitted one or more columns required by gold SQL.",
    ),
    "E03": ErrorCodeInfo(
        code="E03",
        category=ErrorCategory.RETRIEVAL_GROUNDING,
        name="Excessive irrelevant tables",
        description="Grounding retrieved an excessively noisy table schema.",
    ),
    "E04": ErrorCodeInfo(
        code="E04",
        category=ErrorCategory.RETRIEVAL_GROUNDING,
        name="Excessive irrelevant columns",
        description="Grounding retrieved an excessively noisy column schema.",
    ),
    # Relationship / Join
    "E10": ErrorCodeInfo(
        code="E10",
        category=ErrorCategory.RELATIONSHIP_JOIN,
        name="Wrong join path",
        description="Predicted query joins tables through an incorrect relationship path.",
    ),
    "E11": ErrorCodeInfo(
        code="E11",
        category=ErrorCategory.RELATIONSHIP_JOIN,
        name="Wrong relationship role",
        description="Predicted query uses wrong table roles or alias mapping in join.",
    ),
    "E12": ErrorCodeInfo(
        code="E12",
        category=ErrorCategory.RELATIONSHIP_JOIN,
        name="Wrong join key",
        description="Join condition uses wrong columns/keys (e.g. id instead of foreign key).",
    ),
    "E13": ErrorCodeInfo(
        code="E13",
        category=ErrorCategory.RELATIONSHIP_JOIN,
        name="Wrong cardinality/grain",
        description="Join causes fanout/duplication or incorrect aggregation grain.",
    ),
    # Business / Semantic
    "E20": ErrorCodeInfo(
        code="E20",
        category=ErrorCategory.BUSINESS_SEMANTIC,
        name="Wrong business concept",
        description="Misunderstood business logic or domain terminology in question.",
    ),
    "E21": ErrorCodeInfo(
        code="E21",
        category=ErrorCategory.BUSINESS_SEMANTIC,
        name="Wrong measure/aggregation",
        description="Used wrong aggregation function (e.g., SUM vs COUNT vs AVG).",
    ),
    "E22": ErrorCodeInfo(
        code="E22",
        category=ErrorCategory.BUSINESS_SEMANTIC,
        name="Wrong dimension",
        description="Grouped or selected wrong dimensional attribute for reporting.",
    ),
    "E23": ErrorCodeInfo(
        code="E23",
        category=ErrorCategory.BUSINESS_SEMANTIC,
        name="Wrong time semantics",
        description="Incorrect date/time extraction, filter, or interval handling.",
    ),
    # Value / Filter
    "E30": ErrorCodeInfo(
        code="E30",
        category=ErrorCategory.VALUE_FILTER,
        name="Wrong filter column",
        description="Filtered on wrong column name or attribute.",
    ),
    "E31": ErrorCodeInfo(
        code="E31",
        category=ErrorCategory.VALUE_FILTER,
        name="Wrong value grounding",
        description="Literal value in predicate does not match target database value.",
    ),
    "E32": ErrorCodeInfo(
        code="E32",
        category=ErrorCategory.VALUE_FILTER,
        name="Missing predicate",
        description="Omitted a required WHERE or HAVING filter condition.",
    ),
    # SQL Generation
    "E40": ErrorCodeInfo(
        code="E40",
        category=ErrorCategory.SQL_GENERATION,
        name="Logical SQL error",
        description="SQL is valid syntax and executed but produced incorrect output.",
    ),
    "E41": ErrorCodeInfo(
        code="E41",
        category=ErrorCategory.SQL_GENERATION,
        name="Syntax error",
        description="SQL parser or database rejected prediction due to syntax error.",
    ),
    "E42": ErrorCodeInfo(
        code="E42",
        category=ErrorCategory.SQL_GENERATION,
        name="Runtime error",
        description="SQL raised database runtime error (missing function, divide by zero).",
    ),
    "E43": ErrorCodeInfo(
        code="E43",
        category=ErrorCategory.SQL_GENERATION,
        name="Unsupported function/dialect",
        description="LLM hallucinated non-existent function or dialect syntax.",
    ),
    # Evaluation / Environment
    "E90": ErrorCodeInfo(
        code="E90",
        category=ErrorCategory.EVALUATION_ENVIRONMENT,
        name="Evaluator issue",
        description="Prediction is logically valid but evaluator marked incorrect.",
    ),
    "E91": ErrorCodeInfo(
        code="E91",
        category=ErrorCategory.EVALUATION_ENVIRONMENT,
        name="Timeout/environment issue",
        description="Query timed out or failed due to environment infrastructure.",
    ),
}


class LabeledCase(BaseModel):
    """Analysis label assigned to a single benchmark case."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    database_id: str
    question: str
    predicted_sql: str
    gold_sql: str
    execution_correct: bool
    primary_error: str = Field(description="Primary error code (e.g. E01, E10, E40, NONE)")
    secondary_errors: tuple[str, ...] = Field(default_factory=tuple)
    is_manual: bool = False
    reviewer_notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def primary_category(self) -> ErrorCategory:
        """Category corresponding to primary_error code."""
        if self.primary_error == "NONE" or self.execution_correct:
            return ErrorCategory.NONE
        info = TAXONOMY_MAP.get(self.primary_error)
        return info.category if info else ErrorCategory.SQL_GENERATION

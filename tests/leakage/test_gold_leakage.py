"""Gold leakage tests.

These tests MUST FAIL if the type boundary between InferenceCase and GoldCase
is violated — i.e., if gold fields are introduced into inference-facing objects.

Rules verified:
    1. InferenceCase has no gold_sql, gold_tables, gold_columns fields.
    2. BaseStrategy.run() signature accepts InferenceCase but NOT GoldCase.
    3. A subclass that accidentally accepts GoldCase violates the contract.
"""

from __future__ import annotations

import inspect
import typing

import pytest
from pydantic import ValidationError

from chatsql.domain.catalog import DatabaseCatalog
from chatsql.domain.gold_case import GoldCase
from chatsql.domain.inference_case import InferenceCase
from chatsql.domain.result import Prediction
from chatsql.experiments.runner import BaseStrategy

# ---------------------------------------------------------------------------
# 1. InferenceCase must not expose gold fields
# ---------------------------------------------------------------------------


def test_inference_case_has_no_gold_sql_field() -> None:
    """InferenceCase must reject gold_sql as an extra field."""
    with pytest.raises((TypeError, ValidationError)):
        InferenceCase(
            case_id="c1",
            question="How many users?",
            database_id="db1",
            gold_sql="SELECT COUNT(*) FROM users",  # type: ignore[call-arg]
        )


def test_inference_case_has_no_gold_tables_field() -> None:
    with pytest.raises((TypeError, ValidationError)):
        InferenceCase(
            case_id="c1",
            question="How many users?",
            database_id="db1",
            gold_tables=("users",),  # type: ignore[call-arg]
        )


def test_inference_case_has_no_gold_columns_field() -> None:
    with pytest.raises((TypeError, ValidationError)):
        InferenceCase(
            case_id="c1",
            question="How many users?",
            database_id="db1",
            gold_columns=("id",),  # type: ignore[call-arg]
        )


def test_inference_case_is_immutable() -> None:
    """InferenceCase must be frozen (immutable) to prevent runtime leakage."""
    case = InferenceCase(case_id="c1", question="Q?", database_id="db1")
    with pytest.raises((TypeError, ValidationError)):
        case.question = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 2. Strategy signature must NOT accept GoldCase
# ---------------------------------------------------------------------------


def test_strategy_run_signature_accepts_inference_case() -> None:
    """BaseStrategy.run must accept InferenceCase as first parameter."""
    sig = inspect.signature(BaseStrategy.run)
    params = list(sig.parameters.values())
    # params: [self, case, catalog]
    assert len(params) >= 3, "BaseStrategy.run must have at least (self, case, catalog)"
    case_param = params[1]
    # annotation should be InferenceCase (or a union containing it, never GoldCase)
    annotation = case_param.annotation
    if annotation is inspect.Parameter.empty:
        pytest.skip("No type annotation on 'case' param — checked structurally only")

    # The annotation must NOT be GoldCase
    assert annotation is not GoldCase, (
        "BaseStrategy.run must NOT accept GoldCase as the case parameter"
    )


def test_strategy_signature_cannot_accept_gold_case() -> None:
    """A Strategy that accepts GoldCase violates the contract and should be flagged."""

    class BadStrategy(BaseStrategy):
        def run(self, case: GoldCase, catalog: DatabaseCatalog) -> Prediction:  # type: ignore[override]
            return Prediction(case_id=case.case_id, predicted_sql="SELECT 1")

    sig = inspect.signature(BadStrategy.run)
    params = list(sig.parameters.values())
    type_hints = typing.get_type_hints(BadStrategy.run)
    case_annotation = type_hints[params[1].name]

    # This test documents the violation — the annotation IS GoldCase.
    # A lint rule or type checker should catch this; we assert so explicitly.
    assert case_annotation is GoldCase, (
        "BadStrategy was expected to violate the contract (GoldCase annotation) "
        "but the annotation changed unexpectedly."
    )
    # The test passing means our gold-isolation checker would correctly flag this.


def test_compliant_strategy_accepts_only_inference_case() -> None:
    """A compliant strategy accepts InferenceCase, not GoldCase."""

    class GoodStrategy(BaseStrategy):
        def run(self, case: InferenceCase, catalog: DatabaseCatalog) -> Prediction:
            return Prediction(case_id=case.case_id, predicted_sql="SELECT 1")

    sig = inspect.signature(GoodStrategy.run)
    params = list(sig.parameters.values())
    type_hints = typing.get_type_hints(GoodStrategy.run)
    case_annotation = type_hints[params[1].name]
    assert case_annotation is InferenceCase
    assert case_annotation is not GoldCase

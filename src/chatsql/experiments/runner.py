"""BaseStrategy and ExperimentRunner.

Architecture:
    Strategy receives ONLY InferenceCase + DatabaseCatalog.
    GoldCase is NEVER passed to Strategy.
    Executor runs the predicted SQL read-only.
    Evaluator receives Prediction + ExecutionResult + gold fields.
"""

from __future__ import annotations

import abc
from typing import Any

from chatsql.domain.catalog import DatabaseCatalog
from chatsql.domain.gold_case import GoldCase
from chatsql.domain.inference_case import InferenceCase
from chatsql.domain.result import ExecutionResult, ExperimentRecord, Prediction
from chatsql.evaluation.base import BaseEvaluator
from chatsql.execution.base import BaseExecutor
from chatsql.experiments.logger import RunLogger
from chatsql.experiments.manifest import ExperimentManifest
from chatsql.generation.pricing import estimate_cost_usd

__all__ = ["BaseEvaluator", "BaseStrategy", "ExperimentRunner"]


class BaseStrategy(abc.ABC):
    """Abstract base for all Text-to-SQL strategies.

    CRITICAL CONTRACT:
        run() accepts InferenceCase and DatabaseCatalog ONLY.
        It must NOT accept GoldCase or any gold fields.
    """

    @abc.abstractmethod
    def run(self, case: InferenceCase, catalog: DatabaseCatalog) -> Prediction:
        """Generate a SQL prediction for the given inference case."""
        ...


class _RunAggregator:
    """Accumulates the operational metrics required by the experiment protocol."""

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self.total = 0
        self.strategy_errors = 0
        self.executed = 0
        self.invalid_sql = 0
        self.rejected_sql = 0
        self.execution_failed = 0
        self.execution_correct = 0
        self.latency_seconds = 0.0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.schema_tokens = 0
        self.cost_usd = 0.0
        self.cost_unknown = 0

    def observe(
        self,
        prediction: Prediction,
        execution: ExecutionResult,
        metrics: dict[str, Any],
    ) -> None:
        self.latency_seconds += prediction.latency_seconds or 0.0
        self.prompt_tokens += prediction.prompt_tokens or 0
        self.completion_tokens += prediction.completion_tokens or 0
        self.schema_tokens += int(prediction.metadata.get("schema_token_estimate") or 0)

        cost = estimate_cost_usd(
            self._model_name, prediction.prompt_tokens, prediction.completion_tokens
        )
        if cost is None:
            self.cost_unknown += 1
        else:
            self.cost_usd += cost

        if execution.executed:
            self.executed += 1
        elif execution.error_kind == "invalid_sql":
            self.invalid_sql += 1
        elif execution.error_kind == "rejected":
            self.rejected_sql += 1
        else:
            self.execution_failed += 1

        if metrics.get("execution_correct"):
            self.execution_correct += 1

    def as_dict(self) -> dict[str, Any]:
        scored = self.total or 1
        return {
            "total": self.total,
            "errors": self.strategy_errors,
            "executed": self.executed,
            "invalid_sql": self.invalid_sql,
            "rejected_sql": self.rejected_sql,
            "execution_failed": self.execution_failed,
            "execution_correct": self.execution_correct,
            "execution_accuracy": round(self.execution_correct / scored, 4),
            "execution_success_rate": round(self.executed / scored, 4),
            "invalid_sql_rate": round((self.invalid_sql + self.rejected_sql) / scored, 4),
            "sum_latency_seconds": round(self.latency_seconds, 3),
            "mean_latency_seconds": round(self.latency_seconds / scored, 3),
            "sum_prompt_tokens": self.prompt_tokens,
            "sum_completion_tokens": self.completion_tokens,
            "sum_schema_context_tokens": self.schema_tokens,
            "estimated_cost_usd": round(self.cost_usd, 6),
            "cost_estimate_complete": self.cost_unknown == 0,
        }


class ExperimentRunner:
    """Orchestrates a full benchmark run: strategy -> executor -> evaluator -> log."""

    def __init__(
        self,
        strategy: BaseStrategy,
        evaluator: BaseEvaluator,
        logger: RunLogger,
        executor: BaseExecutor,
    ) -> None:
        self.strategy = strategy
        self.evaluator = evaluator
        self.logger = logger
        self.executor = executor

    def run(
        self,
        manifest: ExperimentManifest,
        cases: list[InferenceCase],
        # gold is a parallel list - evaluator-only access
        golds: list[GoldCase],
        catalogs: dict[str, DatabaseCatalog],
    ) -> list[ExperimentRecord]:
        """Execute all cases, log every artifact, return ExperimentRecords."""
        self.logger.write_manifest(manifest)

        records: list[ExperimentRecord] = []
        aggregate = _RunAggregator(model_name=manifest.model.name)

        for case, gold in zip(cases, golds, strict=True):
            if case.case_id != gold.case_id:
                raise ValueError(
                    f"case/gold mismatch: inference case {case.case_id!r} "
                    f"paired with gold case {gold.case_id!r}"
                )

            aggregate.total += 1

            # --- Strategy step (zero gold access) ---
            try:
                catalog = catalogs[case.database_id]
                prediction = self.strategy.run(case, catalog)
            except Exception as exc:  # noqa: BLE001 - recorded per case, run continues
                self.logger.log_error(
                    {"case_id": case.case_id, "component": "strategy", "error": str(exc)}
                )
                records.append(
                    ExperimentRecord(
                        case_id=case.case_id,
                        database_id=case.database_id,
                        question=case.question,
                        predicted_sql="",
                        executed=False,
                        execution_correct=False,
                        error=str(exc),
                    )
                )
                aggregate.strategy_errors += 1
                continue

            self.logger.log_prediction(prediction.model_dump())
            context_view = prediction.metadata.get("context_view")
            if isinstance(context_view, dict):
                self.logger.log_context_view(
                    {
                        "case_id": case.case_id,
                        "database_id": case.database_id,
                        "prompt_version": prediction.metadata.get("prompt_version"),
                        **context_view,
                    }
                )
            self.logger.log_raw_output(
                {
                    "case_id": case.case_id,
                    "model": prediction.metadata.get("model"),
                    "prompt_version": prediction.metadata.get("prompt_version"),
                    "raw_response": prediction.metadata.get("raw_response", ""),
                }
            )

            # --- Execution step (read-only guard + timeout) ---
            execution = self.executor.execute(
                prediction.predicted_sql, case.database_id, case.case_id
            )
            self.logger.log_execution(execution.model_dump())

            # --- Evaluator step (receives gold) ---
            metrics = self.evaluator.evaluate(
                prediction=prediction,
                execution=execution,
                gold_sql=gold.gold_sql,
                gold_tables=gold.gold_tables,
                gold_columns=gold.gold_columns,
            )
            if metrics.get("error") and not execution.executed:
                self.logger.log_error(
                    {
                        "case_id": case.case_id,
                        "component": "execution",
                        "error_kind": execution.error_kind,
                        "error": execution.error,
                    }
                )

            aggregate.observe(prediction, execution, metrics)
            records.append(
                ExperimentRecord(
                    case_id=case.case_id,
                    database_id=case.database_id,
                    question=case.question,
                    predicted_sql=prediction.predicted_sql,
                    executed=execution.executed,
                    execution_correct=bool(metrics.get("execution_correct", False)),
                    error=execution.error,
                    latency_seconds=prediction.latency_seconds,
                    metadata=metrics,
                )
            )

        self.logger.write_metrics(aggregate.as_dict())
        return records

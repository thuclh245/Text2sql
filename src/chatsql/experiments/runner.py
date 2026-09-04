"""BaseStrategy and ExperimentRunner.

Architecture:
    Strategy receives ONLY InferenceCase + DatabaseCatalog.
    GoldCase is NEVER passed to Strategy.
    Evaluator receives Prediction + GoldCase (never touches Strategy).
"""

from __future__ import annotations

import abc
from typing import Any

from chatsql.domain.catalog import DatabaseCatalog
from chatsql.domain.gold_case import GoldCase
from chatsql.domain.inference_case import InferenceCase
from chatsql.domain.result import ExecutionResult, ExperimentRecord, Prediction
from chatsql.experiments.logger import RunLogger
from chatsql.experiments.manifest import ExperimentManifest


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


class BaseEvaluator(abc.ABC):
    """Abstract base for all evaluators.

    Evaluators are the ONLY components allowed to access GoldCase.
    """

    @abc.abstractmethod
    def evaluate(
        self,
        prediction: Prediction,
        execution: ExecutionResult,
        gold_sql: str,
        gold_tables: tuple[str, ...],
        gold_columns: tuple[str, ...],
    ) -> dict[str, Any]:
        """Return a dict of metric values for one case."""
        ...


class ExperimentRunner:
    """Orchestrates a full benchmark run.

    Usage::
        runner = ExperimentRunner(strategy, evaluator, logger)
        runner.run(cases, golds, catalogs, manifest)
    """

    def __init__(
        self,
        strategy: BaseStrategy,
        evaluator: BaseEvaluator,
        logger: RunLogger,
    ) -> None:
        self.strategy = strategy
        self.evaluator = evaluator
        self.logger = logger

    def run(
        self,
        manifest: ExperimentManifest,
        cases: list[InferenceCase],
        # gold is a parallel list — evaluator-only access
        golds: list[GoldCase],
        catalogs: dict[str, DatabaseCatalog],
    ) -> list[ExperimentRecord]:
        """Execute all cases, log every artifact, return ExperimentRecords."""
        self.logger.write_manifest(manifest)

        records: list[ExperimentRecord] = []
        aggregate_metrics: dict[str, Any] = {"total": 0, "executed": 0, "errors": 0}

        for case, gold in zip(cases, golds, strict=True):
            if case.case_id != gold.case_id:
                raise ValueError(
                    f"case/gold mismatch: inference case {case.case_id!r} "
                    f"paired with gold case {gold.case_id!r}"
                )

            aggregate_metrics["total"] += 1

            # --- Strategy step (zero gold access) ---
            try:
                catalog = catalogs[case.database_id]
                prediction = self.strategy.run(case, catalog)
            except Exception as exc:
                self.logger.log_error(
                    {"case_id": case.case_id, "component": "strategy", "error": str(exc)}
                )
                record = ExperimentRecord(
                    case_id=case.case_id,
                    database_id=case.database_id,
                    question=case.question,
                    predicted_sql="",
                    executed=False,
                    execution_correct=False,
                    error=str(exc),
                )
                records.append(record)
                aggregate_metrics["errors"] += 1
                continue

            self.logger.log_prediction(prediction.model_dump())

            # --- Execution stub (benchmark executors replace this in later work) ---
            execution = ExecutionResult(
                case_id=case.case_id,
                executed=False,
                error="Executor not implemented in the foundation runner",
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

            record = ExperimentRecord(
                case_id=case.case_id,
                database_id=case.database_id,
                question=case.question,
                predicted_sql=prediction.predicted_sql,
                executed=execution.executed,
                execution_correct=metrics.get("execution_correct", False),
                error=execution.error,
                latency_seconds=prediction.latency_seconds,
                metadata=metrics,
            )
            records.append(record)
            if execution.executed:
                aggregate_metrics["executed"] += 1

        self.logger.write_metrics(aggregate_metrics)
        return records

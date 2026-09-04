"""CHATSQL CLI entry point."""

from __future__ import annotations

import datetime
import uuid
from pathlib import Path
from typing import Annotated, Any

import typer

import chatsql.strategies  # noqa: F401 - imported for @register side effects
from chatsql import __version__
from chatsql.benchmarks.bird import BirdLoader, BirdPaths, BirdValidator, load_catalogs
from chatsql.config.loader import load_and_hash
from chatsql.evaluation.bird import BirdEXEvaluator
from chatsql.execution import ReadOnlySQLiteExecutor
from chatsql.experiments.logger import RunLogger
from chatsql.experiments.manifest import build_manifest
from chatsql.experiments.registry import get_strategy, list_strategies
from chatsql.experiments.runner import ExperimentRunner
from chatsql.generation.llm_client import build_llm_client
from chatsql.provenance import sha256_file, short_hash

BIRD_MINI_DEV_SQLITE = "bird_mini_dev_sqlite_select_500"

app = typer.Typer(help="CHATSQL research harness.")
benchmark_app = typer.Typer(help="Benchmark management commands.")
experiment_app = typer.Typer(help="Experiment execution commands.")


@app.callback(invoke_without_command=True)
def main(
    version: Annotated[
        bool,
        typer.Option("--version", help="Show the CHATSQL version."),
    ] = False,
) -> None:
    if version:
        typer.echo(__version__)
        raise typer.Exit()


@benchmark_app.command("validate")
def benchmark_validate(
    benchmark: Annotated[
        str,
        typer.Option("--benchmark", help="Benchmark identifier."),
    ] = BIRD_MINI_DEV_SQLITE,
    repo_root: Annotated[
        Path | None,
        typer.Option("--repo-root", help="Repository root. Defaults to auto-detection."),
    ] = None,
    data_dir: Annotated[
        Path | None,
        typer.Option("--data-dir", help="Path to the mini_dev_data directory."),
    ] = None,
    skip_catalogs: Annotated[
        bool,
        typer.Option("--skip-catalogs", help="Skip SQLite catalog introspection."),
    ] = False,
) -> None:
    """Validate BIRD dataset integrity before running experiments."""
    _require_benchmark(benchmark)

    paths = BirdPaths.from_repo_root(repo_root)
    if data_dir is not None:
        paths = BirdPaths(paths.root, data_dir=data_dir)

    try:
        cases, golds = BirdLoader(paths).load_from_split("mini_dev_sqlite", select_only=True)
    except FileNotFoundError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    result = BirdValidator(paths.db_root()).validate(
        cases,
        golds,
        check_catalogs=not skip_catalogs,
    )
    typer.echo(result.summary())
    raise typer.Exit(code=0 if result.is_valid else 1)


@experiment_app.command("run")
def experiment_run(
    benchmark: Annotated[str, typer.Option("--benchmark", help="Benchmark identifier.")],
    strategy: Annotated[str, typer.Option("--strategy", help="Registered strategy name.")],
    config: Annotated[Path, typer.Option("--config", help="Path to experiment YAML config.")],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Validate config + wiring only, do not run."),
    ] = False,
    limit: Annotated[
        int | None,
        typer.Option("--limit", help="Run only the first N cases (smoke test)."),
    ] = None,
) -> None:
    """Run a Text-to-SQL experiment from a versioned config."""
    cfg, cfg_hash = load_and_hash(config)
    typer.echo(f"Config loaded: {config} (hash: {short_hash(cfg_hash)})")

    _require_benchmark(benchmark)
    strategy_cls = _resolve_strategy(strategy)
    _cross_check_config_strategy(cfg, strategy)

    benchmark_cfg = cfg.get("benchmark", {})
    model_cfg = cfg.get("model", {})
    execution_cfg = cfg.get("execution", {})
    experiment_cfg = cfg.get("experiment", {})

    revision = _require_config_value(benchmark_cfg, "benchmark.revision")
    evaluator_revision = _require_config_value(benchmark_cfg, "benchmark.evaluator_revision")

    paths = BirdPaths.from_repo_root()
    split = benchmark_cfg.get("split", "mini_dev_sqlite")
    select_only = benchmark_cfg.get("select_only", True)

    question_path = paths.question_json(split)
    if not question_path.exists():
        typer.echo(f"BIRD question file not found: {question_path}")
        raise typer.Exit(code=1)
    data_hash = sha256_file(question_path)

    cases, golds = BirdLoader(paths).load_from_split(split, select_only=select_only)
    if limit is not None:
        cases = cases[:limit]
    if not cases:
        typer.echo("No cases to run.")
        raise typer.Exit(code=1)

    db_ids = sorted({case.database_id for case in cases})
    catalogs, catalog_failures = load_catalogs(paths.db_root(), db_ids)
    if catalog_failures:
        typer.echo("Catalog load failed for:\n  " + "\n  ".join(catalog_failures))
        raise typer.Exit(code=1)

    executor = ReadOnlySQLiteExecutor(
        db_root=paths.db_root(),
        timeout_seconds=execution_cfg.get("timeout_seconds", 30.0),
        row_limit=execution_cfg.get("row_limit", execution_cfg.get("max_rows", 10_000)),
    )
    strategy_impl = strategy_cls(build_llm_client(model_cfg))
    evaluator = BirdEXEvaluator(
        executor=executor,
        case_database_ids={case.case_id: case.database_id for case in cases},
    )

    timestamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
    id_prefix = experiment_cfg.get("id_prefix", strategy)
    run_id = f"{id_prefix}_{timestamp}_{uuid.uuid4().hex[:6]}"
    manifest = build_manifest(
        experiment_id=run_id,
        seed=experiment_cfg.get("seed", 42),
        benchmark_name=benchmark,
        benchmark_revision=revision,
        benchmark_data_hash=data_hash,
        evaluator_revision=evaluator_revision,
        strategy_name=strategy,
        strategy_config=cfg,
        model_provider=model_cfg.get("provider", "openai"),
        model_name=model_cfg.get("name", "gpt-4o-mini"),
        model_revision=model_cfg.get("revision", "unknown"),
        model_temperature=model_cfg.get("temperature", 0.0),
    )

    runs_dir = Path(cfg.get("output", {}).get("runs_dir", "runs"))
    logger = RunLogger(runs_root=runs_dir, run_id=run_id)

    if dry_run:
        typer.echo(
            f"Dry-run OK: {len(cases)} cases, {len(db_ids)} databases, "
            f"strategy={strategy}, data_hash={short_hash(data_hash)}"
        )
        raise typer.Exit()

    runner = ExperimentRunner(
        strategy=strategy_impl,
        evaluator=evaluator,
        logger=logger,
        executor=executor,
    )
    records = runner.run(
        manifest=manifest,
        cases=cases,
        golds=[golds[case.case_id] for case in cases],
        catalogs=catalogs,
    )

    total = len(records)
    correct = sum(1 for record in records if record.execution_correct)
    score = (correct / total * 100) if total else 0.0
    typer.echo(f"Results: {correct}/{total} correct ({score:.1f}% EX)")
    typer.echo(f"Artifacts: {logger.run_dir}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_benchmark(benchmark: str) -> None:
    if benchmark != BIRD_MINI_DEV_SQLITE:
        raise typer.BadParameter(f"supported benchmark identifiers: {BIRD_MINI_DEV_SQLITE}")


def _resolve_strategy(strategy: str) -> Any:
    try:
        return get_strategy(strategy)
    except KeyError as exc:
        raise typer.BadParameter(
            f"unknown strategy {strategy!r}; registered: {', '.join(list_strategies())}"
        ) from exc


def _cross_check_config_strategy(cfg: dict[str, Any], strategy: str) -> None:
    configured = cfg.get("strategy", {}).get("name")
    if configured is not None and configured != strategy:
        raise typer.BadParameter(
            f"--strategy {strategy!r} does not match config strategy.name {configured!r}"
        )


def _require_config_value(section: dict[str, Any], dotted_key: str) -> Any:
    key = dotted_key.split(".")[-1]
    value = section.get(key)
    if value is None or value == "":
        raise typer.BadParameter(f"config is missing required key: {dotted_key}")
    return value


app.add_typer(benchmark_app, name="benchmark")
app.add_typer(experiment_app, name="experiment")

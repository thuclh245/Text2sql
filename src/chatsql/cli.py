"""CHATSQL CLI entry point."""

from __future__ import annotations

import datetime
import uuid
from pathlib import Path
from typing import Annotated, Any

import typer

import chatsql.grounding.full_schema  # noqa: F401 - imported for @register side effects
import chatsql.grounding.lite_sql_adapter  # noqa: F401 - imported for @register side effects
import chatsql.grounding.simple_dense  # noqa: F401 - imported for @register side effects
import chatsql.strategies  # noqa: F401 - imported for @register side effects
from chatsql import __version__
from chatsql.benchmarks.bird import BirdLoader, BirdPaths, BirdValidator, load_catalogs
from chatsql.config.loader import load_and_hash
from chatsql.evaluation.bird import BirdEXEvaluator
from chatsql.execution import ReadOnlySQLiteExecutor
from chatsql.experiments.logger import RunLogger
from chatsql.experiments.manifest import build_manifest
from chatsql.experiments.registry import get_strategy, list_strategies
from chatsql.experiments.runner import ExperimentRunner, _project_catalog
from chatsql.generation.llm_client import build_llm_client
from chatsql.generation.pricing import estimate_cost_usd
from chatsql.generation.prompt_builder import FullSchemaPromptBuilder
from chatsql.generation.token_estimator import estimate_chat_prompt_tokens
from chatsql.grounding.registry import get_grounder, list_grounders
from chatsql.provenance import sha256_file, short_hash

BIRD_MINI_DEV_SQLITE = "bird_mini_dev_sqlite_select_500"

_BENCHMARK_ALIASES = {
    BIRD_MINI_DEV_SQLITE: BIRD_MINI_DEV_SQLITE,
    "bird-mini-dev-sqlite-500": BIRD_MINI_DEV_SQLITE,
}
_STRATEGY_ALIASES = {
    "full_schema": "full_schema",
    "full-schema": "full_schema",
    "full_schema_control": "full_schema",
}
_GROUNDER_ALIASES = {
    "full_schema": "full-schema",
    "full-schema": "full-schema",
    "simple_dense": "simple-dense",
    "simple-dense": "simple-dense",
    "lite_sql": "lite-sql",
    "lite-sql": "lite-sql",
}

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

    benchmark = _normalize_benchmark(benchmark)
    strategy = _normalize_strategy(strategy)
    _cross_check_config_benchmark(cfg, benchmark)
    strategy_cls = _resolve_strategy(strategy)
    _cross_check_config_strategy(cfg, strategy)

    benchmark_cfg = cfg.get("benchmark", {})
    model_cfg = cfg.get("model", {})
    execution_cfg = cfg.get("execution", {})
    experiment_cfg = cfg.get("experiment", {})
    grounder_cfg = cfg.get("grounder", {"name": "full-schema"})

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
    grounder_name = _normalize_grounder(_require_config_value(grounder_cfg, "grounder.name"))
    grounder = _build_grounder(grounder_name, grounder_cfg)
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
        grounder_name=grounder_name,
        strategy_config={**cfg, "grounder": {**grounder_cfg, "name": grounder_name}},
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
            f"strategy={strategy}, grounder={grounder_name}, data_hash={short_hash(data_hash)}"
        )
        raise typer.Exit()

    runner = ExperimentRunner(
        strategy=strategy_impl,
        evaluator=evaluator,
        logger=logger,
        executor=executor,
        grounder=grounder,
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


@experiment_app.command("estimate-tokens")
def experiment_estimate_tokens(
    benchmark: Annotated[str, typer.Option("--benchmark", help="Benchmark identifier.")],
    strategy: Annotated[str, typer.Option("--strategy", help="Registered strategy name.")],
    config: Annotated[Path, typer.Option("--config", help="Path to experiment YAML config.")],
    limit: Annotated[
        int | None,
        typer.Option("--limit", help="Estimate only the first N cases."),
    ] = None,
) -> None:
    """Estimate prompt/output tokens for an experiment without calling a model."""
    cfg, cfg_hash = load_and_hash(config)
    benchmark = _normalize_benchmark(benchmark)
    strategy = _normalize_strategy(strategy)
    if strategy != "full_schema":
        raise typer.BadParameter("token estimation currently supports strategy=full_schema")
    _cross_check_config_benchmark(cfg, benchmark)
    _cross_check_config_strategy(cfg, strategy)

    benchmark_cfg = cfg.get("benchmark", {})
    model_cfg = cfg.get("model", {})
    grounder_cfg = cfg.get("grounder", {"name": "full-schema"})
    paths = BirdPaths.from_repo_root()
    split = benchmark_cfg.get("split", "mini_dev_sqlite")
    select_only = benchmark_cfg.get("select_only", True)

    cases, _ = BirdLoader(paths).load_from_split(split, select_only=select_only)
    if limit is not None:
        cases = cases[:limit]
    if not cases:
        typer.echo("No cases to estimate.")
        raise typer.Exit(code=1)

    db_ids = sorted({case.database_id for case in cases})
    catalogs, catalog_failures = load_catalogs(paths.db_root(), db_ids)
    if catalog_failures:
        typer.echo("Catalog load failed for:\n  " + "\n  ".join(catalog_failures))
        raise typer.Exit(code=1)

    grounder_name = _normalize_grounder(_require_config_value(grounder_cfg, "grounder.name"))
    grounder = _build_grounder(grounder_name, grounder_cfg)
    model_name = model_cfg.get("name", "gpt-4o-mini")
    max_completion_tokens = int(model_cfg.get("max_tokens", 1024))
    prompt_builder = FullSchemaPromptBuilder()

    prompt_tokens_total = 0
    total_tokens_total = 0
    estimated_cost_total = 0.0
    cost_unknown = 0
    largest_case: tuple[str, int] = ("", 0)

    for case in cases:
        catalog = catalogs[case.database_id]
        grounded_catalog = _project_catalog(catalog, grounder.ground(case, catalog))
        prompt, _ = prompt_builder.build(case, grounded_catalog)
        prompt_tokens = estimate_chat_prompt_tokens(prompt, model_name)
        total_tokens = prompt_tokens + max_completion_tokens
        prompt_tokens_total += prompt_tokens
        total_tokens_total += total_tokens
        if prompt_tokens > largest_case[1]:
            largest_case = (case.case_id, prompt_tokens)

        cost = estimate_cost_usd(model_name, prompt_tokens, max_completion_tokens)
        if cost is None:
            cost_unknown += 1
        else:
            estimated_cost_total += cost

    count = len(cases)
    typer.echo(f"Config hash: {short_hash(cfg_hash)}")
    typer.echo(f"Cases estimated: {count}")
    typer.echo(f"Model: {model_name}")
    typer.echo(f"Grounder: {grounder_name}")
    typer.echo(f"Max completion tokens/call: {max_completion_tokens}")
    typer.echo(f"Prompt tokens estimated: {prompt_tokens_total}")
    typer.echo(f"Mean prompt tokens/call: {prompt_tokens_total / count:.1f}")
    typer.echo(f"Total tokens estimated: {total_tokens_total}")
    typer.echo(f"Mean total tokens/call: {total_tokens_total / count:.1f}")
    typer.echo(f"Largest prompt case: {largest_case[0]} ({largest_case[1]} tokens)")
    if cost_unknown:
        typer.echo("Estimated cost: unknown for this model")
    else:
        typer.echo(f"Estimated cost before call: ${estimated_cost_total:.6f}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_benchmark(benchmark: str) -> None:
    _normalize_benchmark(benchmark)


def _normalize_benchmark(benchmark: str) -> str:
    try:
        return _BENCHMARK_ALIASES[benchmark]
    except KeyError as exc:
        supported = ", ".join(sorted(_BENCHMARK_ALIASES))
        raise typer.BadParameter(f"supported benchmark identifiers: {supported}") from exc


def _normalize_strategy(strategy: str) -> str:
    return _STRATEGY_ALIASES.get(strategy, strategy)


def _normalize_grounder(grounder: str) -> str:
    return _GROUNDER_ALIASES.get(grounder, grounder)


def _resolve_strategy(strategy: str) -> Any:
    try:
        return get_strategy(strategy)
    except KeyError as exc:
        raise typer.BadParameter(
            f"unknown strategy {strategy!r}; registered: {', '.join(list_strategies())}"
        ) from exc


def _build_grounder(grounder: str, config: dict[str, Any]) -> Any:
    grounder_cls = _resolve_grounder(grounder)
    params = {key: value for key, value in config.items() if key != "name"}
    try:
        return grounder_cls(**params)
    except TypeError as exc:
        raise typer.BadParameter(
            f"invalid config for grounder {grounder!r}: {exc}"
        ) from exc


def _resolve_grounder(grounder: str) -> Any:
    try:
        return get_grounder(grounder)
    except KeyError as exc:
        raise typer.BadParameter(
            f"unknown grounder {grounder!r}; registered: {', '.join(list_grounders())}"
        ) from exc


def _cross_check_config_strategy(cfg: dict[str, Any], strategy: str) -> None:
    configured = cfg.get("strategy", {}).get("name")
    if configured is not None and _normalize_strategy(configured) != strategy:
        raise typer.BadParameter(
            f"--strategy {strategy!r} does not match config strategy.name {configured!r}"
        )


def _cross_check_config_benchmark(cfg: dict[str, Any], benchmark: str) -> None:
    configured = cfg.get("benchmark", {}).get("name")
    if configured is not None and _normalize_benchmark(configured) != benchmark:
        raise typer.BadParameter(
            f"--benchmark {benchmark!r} does not match config benchmark.name {configured!r}"
        )


def _require_config_value(section: dict[str, Any], dotted_key: str) -> Any:
    key = dotted_key.split(".")[-1]
    value = section.get(key)
    if value is None or value == "":
        raise typer.BadParameter(f"config is missing required key: {dotted_key}")
    return value


app.add_typer(benchmark_app, name="benchmark")
app.add_typer(experiment_app, name="experiment")

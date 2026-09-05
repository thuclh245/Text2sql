"""CHATSQL CLI entry point."""

from __future__ import annotations

import datetime
import uuid
from pathlib import Path
from typing import Annotated, Any

import typer

import chatsql.grounding.full_schema  # noqa: F401 - imported for @register side effects
import chatsql.grounding.lite_sql_adapter  # noqa: F401 - imported for @register side effects
import chatsql.grounding.relationship_aware  # noqa: F401 - imported for @register side effects
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
    "relationship_aware": "relationship_aware",
    "relationship-aware": "relationship_aware",
}
_GROUNDER_ALIASES = {
    "full_schema": "full-schema",
    "full-schema": "full-schema",
    "simple_dense": "simple-dense",
    "simple-dense": "simple-dense",
    "lite_sql": "lite-sql",
    "lite-sql": "lite-sql",
    "relationship_aware": "relationship-aware",
    "relationship-aware": "relationship-aware",
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

    grounder_name = _normalize_grounder(_require_config_value(grounder_cfg, "grounder.name"))

    if dry_run:
        typer.echo(
            f"Dry-run OK: {len(cases)} cases, {len(db_ids)} databases, "
            f"strategy={strategy}, grounder={grounder_name}, data_hash={short_hash(data_hash)}"
        )
        raise typer.Exit()

    executor = ReadOnlySQLiteExecutor(
        db_root=paths.db_root(),
        timeout_seconds=execution_cfg.get("timeout_seconds", 30.0),
        row_limit=execution_cfg.get("row_limit", execution_cfg.get("max_rows", 10_000)),
    )
    grounder = _build_grounder(grounder_name, grounder_cfg)
    strategy_cfg = cfg.get("strategy", {})
    strategy_impl = _build_strategy(strategy_cls, build_llm_client(model_cfg), strategy_cfg)
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


def _build_strategy(
    strategy_cls: Any,
    llm_client: Any,
    strategy_cfg: dict[str, Any],
) -> Any:
    """Instantiate a strategy, forwarding a ``strategy.reasoner`` config block if set.

    Only ``relationship_aware``-family strategies accept a ``reasoner_config``
    kwarg (used by the Phase 7B ablation configs to toggle role disambiguation,
    grain validation, and bridge expansion); other strategies take just the
    LLM client, so the kwarg is only passed when the config declares it.
    """
    reasoner_cfg = strategy_cfg.get("reasoner")
    if reasoner_cfg:
        return strategy_cls(llm_client, reasoner_config=reasoner_cfg)
    return strategy_cls(llm_client)


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
        raise typer.BadParameter(f"invalid config for grounder {grounder!r}: {exc}") from exc


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


analysis_app = typer.Typer(help="Error analysis and diagnostic commands.")


@analysis_app.command("run")
def analysis_run(
    run_dir: Annotated[Path, typer.Option("--run-dir", help="Path to experiment run directory.")],
    output_dir: Annotated[
        Path | None,
        typer.Option("--output-dir", help="Output directory for error analysis artifacts."),
    ] = None,
    db_root: Annotated[
        Path | None,
        typer.Option(
            "--db-root",
            help=(
                "Root directory containing <db_id>/<db_id>.sqlite files. When "
                "given, enables the fine-grained join_relationship slice "
                "(1_hop_join/2_hop_join/3_plus_hop_join/multiple_fk_ambiguity/"
                "bridge_table_required) used by the Phase 7A/7B gates; "
                "otherwise those gates fall back to the coarser table_slice/"
                "join_depth dimensions."
            ),
        ),
    ] = None,
) -> None:
    """Analyze a run directory and generate error analysis artifacts."""
    from chatsql.analysis.reports import analyze_run_directory

    if not run_dir.exists():
        typer.echo(f"Run directory not found: {run_dir}")
        raise typer.Exit(code=1)

    catalogs = None
    if db_root is not None:
        db_ids = sorted(p.name for p in db_root.iterdir() if p.is_dir())
        catalogs, catalog_failures = load_catalogs(db_root, db_ids)
        for failure in catalog_failures:
            typer.echo(f"Warning: could not load catalog for {failure}")

    summary = analyze_run_directory(run_dir=run_dir, output_dir=output_dir, catalogs=catalogs)
    target_out = output_dir if output_dir is not None else run_dir / "error_analysis"

    typer.echo(f"Error Analysis complete for: {run_dir.name}")
    typer.echo(f"Accuracy: {summary['accuracy_pct']}% EX")
    typer.echo("Error Budget:")
    for cat, pct in summary["error_budget_pct"].items():
        typer.echo(f"  - {cat}: {pct}%")
    dec = summary["decision"]
    track_name = dec.get("recommended_track_name", "")
    typer.echo(f"\nRecommended Research Track: {dec['recommended_track']} ({track_name})")
    typer.echo(f"Reason: {dec['reason']}")
    typer.echo(f"Artifacts saved to: {target_out}")


@analysis_app.command("view")
def analysis_view(
    run_dir: Annotated[Path, typer.Option("--run-dir", help="Path to experiment run directory.")],
    case_id: Annotated[
        str | None,
        typer.Option("--case-id", help="Filter by specific case ID."),
    ] = None,
    error_code: Annotated[
        str | None,
        typer.Option("--error-code", help="Filter by error code (e.g. E01, E10)."),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", help="Maximum cases to display.")] = 5,
    output: Annotated[
        Path | None,
        typer.Option("--output", help="Save review sheet to Markdown file."),
    ] = None,
) -> None:
    """View and inspect cases for manual review audit."""
    import json

    from chatsql.analysis.case_view import export_cases_for_review, render_case_for_review
    from chatsql.analysis.reports import (
        _retrieved_columns_from_grounding,
        _retrieved_tables_from_grounding,
        analyze_run_directory,
    )
    from chatsql.analysis.taxonomy import LabeledCase

    if not run_dir.exists():
        typer.echo(f"Run directory not found: {run_dir}")
        raise typer.Exit(code=1)

    labels_file = run_dir / "error_analysis" / "labeled_cases.jsonl"
    if not labels_file.exists():
        analyze_run_directory(run_dir)

    cases: list[LabeledCase] = []
    with labels_file.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                item = json.loads(line)
                c = LabeledCase.model_validate(item)
                if case_id and c.case_id != case_id:
                    continue
                if error_code and c.primary_error != error_code:
                    continue
                cases.append(c)

    if not cases:
        typer.echo("No matching cases found.")
        return

    def _load_by_case_id(path: Path) -> dict[str, dict[str, Any]]:
        records: dict[str, dict[str, Any]] = {}
        if not path.exists():
            return records
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    records[item["case_id"]] = item
        return records

    groundings_by_id = _load_by_case_id(run_dir / "groundings.jsonl")
    executions_by_id = _load_by_case_id(run_dir / "executions.jsonl")

    case_context: dict[str, dict[str, Any]] = {}
    for c in cases:
        gr_record = groundings_by_id.get(c.case_id, {})
        exec_record = executions_by_id.get(c.case_id)
        retrieved_tables = _retrieved_tables_from_grounding(gr_record)
        retrieved_columns = _retrieved_columns_from_grounding(gr_record)
        case_context[c.case_id] = {
            "retrieved_tables": tuple(retrieved_tables) if retrieved_tables is not None else None,
            "retrieved_columns": tuple(retrieved_columns)
            if retrieved_columns is not None
            else None,
            "execution_info": exec_record,
        }

    if output is not None:
        export_cases_for_review(cases, output_path=output, limit=limit, case_context=case_context)
        typer.echo(f"Exported {min(len(cases), limit)} cases to {output}")
        return

    for c in cases[:limit]:
        ctx = case_context.get(c.case_id, {})
        typer.echo(
            render_case_for_review(
                c,
                retrieved_tables=ctx.get("retrieved_tables"),
                retrieved_columns=ctx.get("retrieved_columns"),
                execution_info=ctx.get("execution_info"),
            )
        )


@analysis_app.command("label")
def analysis_label(
    run_dir: Annotated[Path, typer.Option("--run-dir", help="Path to experiment run directory.")],
    case_id: Annotated[str, typer.Option("--case-id", help="Case ID to correct.")],
    primary_error: Annotated[
        str | None,
        typer.Option("--primary-error", help="Corrected primary error code (e.g. E01, NONE)."),
    ] = None,
    notes: Annotated[
        str | None,
        typer.Option("--notes", help="Reviewer notes explaining the correction."),
    ] = None,
) -> None:
    """Persist a manual reviewer correction to a case's error label."""
    from chatsql.analysis.reports import apply_manual_label
    from chatsql.analysis.taxonomy import TAXONOMY_MAP

    analysis_dir = run_dir / "error_analysis"
    if not (analysis_dir / "labeled_cases.jsonl").exists():
        typer.echo(
            f"No labeled_cases.jsonl found under {analysis_dir}. Run `chatsql analysis run` first."
        )
        raise typer.Exit(code=1)

    if primary_error is not None and primary_error != "NONE" and primary_error not in TAXONOMY_MAP:
        typer.echo(f"Unknown error code: {primary_error}")
        raise typer.Exit(code=1)

    try:
        updated = apply_manual_label(
            analysis_dir,
            case_id=case_id,
            primary_error=primary_error,
            reviewer_notes=notes,
        )
    except KeyError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    typer.echo(
        f"Updated case {updated.case_id}: primary_error={updated.primary_error}, "
        f"is_manual={updated.is_manual}"
    )


@analysis_app.command("compare")
def analysis_compare(
    run_a: Annotated[Path, typer.Option("--run-a", help="Path to baseline run directory A.")],
    run_b: Annotated[Path, typer.Option("--run-b", help="Path to candidate run directory B.")],
    output: Annotated[
        Path | None,
        typer.Option("--output", help="Save comparison report to Markdown file."),
    ] = None,
) -> None:
    """Compare error distributions and shifts between two experiment runs."""
    from chatsql.analysis.compare import compare_run_directories, format_error_comparison_md

    if not run_a.exists():
        typer.echo(f"Run directory A not found: {run_a}")
        raise typer.Exit(code=1)
    if not run_b.exists():
        typer.echo(f"Run directory B not found: {run_b}")
        raise typer.Exit(code=1)

    comp = compare_run_directories(run_a, run_b)
    md = format_error_comparison_md(comp)

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(md, encoding="utf-8")
        typer.echo(f"Comparison report saved to: {output}")
    else:
        typer.echo(md)


@analysis_app.command("phase7a-benchmark-gate")
def analysis_relationship_benchmark_gate(
    full_schema_run: Annotated[
        Path,
        typer.Option("--full-schema-run", help="Path to the full_schema control run directory."),
    ],
    relationship_aware_run: Annotated[
        Path,
        typer.Option(
            "--relationship-aware-run",
            help="Path to the relationship_aware candidate run directory.",
        ),
    ],
    output_dir: Annotated[
        Path | None,
        typer.Option("--output-dir", help="Directory for Phase 7A gate report artifacts."),
    ] = None,
    full_schema_name: Annotated[
        str,
        typer.Option("--full-schema-name", help="Display name for the full-schema system."),
    ] = "full_schema",
    relationship_aware_name: Annotated[
        str,
        typer.Option(
            "--relationship-aware-name",
            help="Display name for the relationship-aware system.",
        ),
    ] = "relationship_aware",
) -> None:
    """Generate the Phase 7A benchmark gate from full-schema and relationship-aware runs."""
    from chatsql.analysis.relationship_benchmark_gate import (
        format_relationship_benchmark_gate_report_md,
        generate_relationship_benchmark_gate_report,
        save_relationship_benchmark_gate_report,
    )

    if not full_schema_run.exists():
        typer.echo(f"Full-schema run directory not found: {full_schema_run}")
        raise typer.Exit(code=1)
    if not relationship_aware_run.exists():
        typer.echo(f"Relationship-aware run directory not found: {relationship_aware_run}")
        raise typer.Exit(code=1)

    report = generate_relationship_benchmark_gate_report(
        full_schema_run_dir=full_schema_run,
        relationship_aware_run_dir=relationship_aware_run,
        full_schema_name=full_schema_name,
        relationship_aware_name=relationship_aware_name,
    )
    md = format_relationship_benchmark_gate_report_md(report)

    if output_dir is not None:
        save_relationship_benchmark_gate_report(report, output_dir)
        typer.echo(f"Phase 7A gate report saved to: {output_dir}")
    else:
        typer.echo(md)


@analysis_app.command("phase7b-ablation-gate")
def analysis_relationship_ablation_gate(
    relationship_aware_run: Annotated[
        Path,
        typer.Option(
            "--relationship-aware-run",
            help="Path to the full relationship_aware run directory.",
        ),
    ],
    a1_run: Annotated[
        Path,
        typer.Option("--a1-run", help="Path to the A1 no-role-disambiguation run directory."),
    ],
    a2_run: Annotated[
        Path,
        typer.Option("--a2-run", help="Path to the A2 no-grain-validation run directory."),
    ],
    a3_run: Annotated[
        Path,
        typer.Option("--a3-run", help="Path to the A3 no-bridge-expansion run directory."),
    ],
    output_dir: Annotated[
        Path | None,
        typer.Option("--output-dir", help="Directory for Phase 7B gate report artifacts."),
    ] = None,
    targeted_drop_threshold_pct: Annotated[
        float,
        typer.Option(
            "--targeted-drop-threshold-pct",
            help="Minimum targeted slice EX drop in percentage points.",
        ),
    ] = 5.0,
) -> None:
    """Generate the Phase 7B relationship ablation gate report."""
    from chatsql.analysis.relationship_ablation_gate import (
        format_relationship_ablation_gate_report_md,
        generate_relationship_ablation_gate_report,
        save_relationship_ablation_gate_report,
    )

    for label, run_dir in (
        ("Relationship-aware", relationship_aware_run),
        ("A1", a1_run),
        ("A2", a2_run),
        ("A3", a3_run),
    ):
        if not run_dir.exists():
            typer.echo(f"{label} run directory not found: {run_dir}")
            raise typer.Exit(code=1)

    report = generate_relationship_ablation_gate_report(
        relationship_aware_run_dir=relationship_aware_run,
        a1_run_dir=a1_run,
        a2_run_dir=a2_run,
        a3_run_dir=a3_run,
        targeted_drop_threshold_pct=targeted_drop_threshold_pct,
    )
    md = format_relationship_ablation_gate_report_md(report)

    if output_dir is not None:
        save_relationship_ablation_gate_report(report, output_dir)
        typer.echo(f"Phase 7B ablation gate report saved to: {output_dir}")
    else:
        typer.echo(md)


@analysis_app.command("phase7c-error-analysis")
def analysis_relationship_error_analysis(
    run_dir: Annotated[
        Path,
        typer.Option("--run-dir", help="Path to the run directory to analyze."),
    ],
    output_dir: Annotated[
        Path | None,
        typer.Option("--output-dir", help="Directory for Phase 7C error analysis artifacts."),
    ] = None,
    run_name: Annotated[
        str,
        typer.Option("--run-name", help="Display name for the analyzed run."),
    ] = "relationship_aware",
    db_root: Annotated[
        Path | None,
        typer.Option(
            "--db-root",
            help=(
                "Root directory containing <db_id>/<db_id>.sqlite files. "
                "When given, enables accurate missing-bridge detection via the "
                "relationship graph; otherwise bridge-required cases fall back "
                "into the missing_table/wrong_fk/fanout_grain buckets."
            ),
        ),
    ] = None,
) -> None:
    """Bucket Phase 7C failures by root cause and identify the main bottleneck."""
    from chatsql.analysis.relationship_error_analysis import (
        format_relationship_error_analysis_report_md,
        generate_relationship_error_analysis_report,
        save_relationship_error_analysis_report,
    )
    from chatsql.analysis.reports import load_labeled_cases

    if not run_dir.exists():
        typer.echo(f"Run directory not found: {run_dir}")
        raise typer.Exit(code=1)

    catalogs = None
    if db_root is not None:
        labels_path = run_dir / "error_analysis" / "labeled_cases.jsonl"
        if not labels_path.exists():
            from chatsql.analysis.reports import analyze_run_directory

            analyze_run_directory(run_dir)
        db_ids = sorted({c.database_id for c in load_labeled_cases(labels_path)})
        catalogs, catalog_failures = load_catalogs(db_root, db_ids)
        for failure in catalog_failures:
            typer.echo(f"Warning: could not load catalog for {failure}")

    report = generate_relationship_error_analysis_report(
        run_dir=run_dir,
        catalogs=catalogs,
        run_name=run_name,
    )
    md = format_relationship_error_analysis_report_md(report)

    if output_dir is not None:
        save_relationship_error_analysis_report(report, output_dir)
        typer.echo(f"Phase 7C error analysis report saved to: {output_dir}")
    else:
        typer.echo(md)


def _load_all_catalogs_under(db_root: Path) -> dict[str, Any]:
    db_ids = sorted(p.name for p in db_root.iterdir() if p.is_dir())
    catalogs, catalog_failures = load_catalogs(db_root, db_ids)
    for failure in catalog_failures:
        typer.echo(f"Warning: could not load catalog for {failure}")
    return catalogs


@analysis_app.command("phase7d-slice-metrics")
def analysis_relationship_slice_metrics(
    run_dir: Annotated[
        Path,
        typer.Option("--run-dir", help="Path to the relationship_aware run directory."),
    ],
    db_root: Annotated[
        Path,
        typer.Option(
            "--db-root",
            help="Root directory containing <db_id>/<db_id>.sqlite files.",
        ),
    ],
    output_dir: Annotated[
        Path | None,
        typer.Option("--output-dir", help="Directory for Phase 7D slice-metrics artifacts."),
    ] = None,
    run_name: Annotated[
        str,
        typer.Option("--run-name", help="Display name for the analyzed run."),
    ] = "relationship_aware",
) -> None:
    """Break down relationship-reasoning quality by join slice and find the bottleneck."""
    from chatsql.analysis.relationship_slice_metrics import (
        format_relationship_slice_metrics_report_md,
        generate_relationship_slice_metrics_report,
        save_relationship_slice_metrics_report,
    )

    if not run_dir.exists():
        typer.echo(f"Run directory not found: {run_dir}")
        raise typer.Exit(code=1)
    if not db_root.exists():
        typer.echo(f"DB root not found: {db_root}")
        raise typer.Exit(code=1)

    catalogs = _load_all_catalogs_under(db_root)
    report = generate_relationship_slice_metrics_report(
        run_dir=run_dir,
        catalogs=catalogs,
        run_name=run_name,
    )
    md = format_relationship_slice_metrics_report_md(report)

    if output_dir is not None:
        save_relationship_slice_metrics_report(report, output_dir)
        typer.echo(f"Phase 7D slice-metrics report saved to: {output_dir}")
    else:
        typer.echo(md)


@analysis_app.command("phase7d-hardening-gate")
def analysis_relationship_hardening_gate(
    before_run: Annotated[
        Path,
        typer.Option("--before-run", help="Relationship_aware run directory before the fix."),
    ],
    after_run: Annotated[
        Path,
        typer.Option("--after-run", help="Relationship_aware run directory after the fix."),
    ],
    target_slice: Annotated[
        str,
        typer.Option(
            "--target-slice",
            help=(
                "Join slice the Phase 7D fix targeted, e.g. bridge_table_required, "
                "multiple_fk_ambiguity, 3_plus_hop_join, 2_hop_join, 1_hop_join, single_table."
            ),
        ),
    ],
    db_root: Annotated[
        Path,
        typer.Option(
            "--db-root",
            help="Root directory containing <db_id>/<db_id>.sqlite files.",
        ),
    ],
    output_dir: Annotated[
        Path | None,
        typer.Option("--output-dir", help="Directory for Phase 7D hardening gate artifacts."),
    ] = None,
    regression_tolerance: Annotated[
        float,
        typer.Option(
            "--regression-tolerance",
            help="Maximum allowed quality-score regression on non-target slices.",
        ),
    ] = 0.01,
) -> None:
    """Verify a Phase 7D fix improved its target slice without regressing others."""
    from chatsql.analysis.relationship_slice_metrics import (
        format_relationship_hardening_gate_report_md,
        generate_relationship_hardening_gate_report,
        save_relationship_hardening_gate_report,
    )

    for label, run_dir in (("Before", before_run), ("After", after_run)):
        if not run_dir.exists():
            typer.echo(f"{label} run directory not found: {run_dir}")
            raise typer.Exit(code=1)
    if not db_root.exists():
        typer.echo(f"DB root not found: {db_root}")
        raise typer.Exit(code=1)

    catalogs = _load_all_catalogs_under(db_root)
    try:
        report = generate_relationship_hardening_gate_report(
            before_run_dir=before_run,
            after_run_dir=after_run,
            catalogs=catalogs,
            target_slice=target_slice,
            regression_tolerance=regression_tolerance,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    md = format_relationship_hardening_gate_report_md(report)

    if output_dir is not None:
        save_relationship_hardening_gate_report(report, output_dir)
        typer.echo(f"Phase 7D hardening gate report saved to: {output_dir}")
    else:
        typer.echo(md)


@analysis_app.command("memo")
def analysis_memo(
    run_dir: Annotated[Path, typer.Option("--run-dir", help="Path to experiment run directory.")],
    baseline: Annotated[
        str,
        typer.Option("--baseline", help="Baseline name for the memo."),
    ] = "B0 Full-Schema Control",
    output: Annotated[
        Path | None,
        typer.Option("--output", help="Save memo to Markdown file."),
    ] = None,
) -> None:
    """Generate the scientific research decision memo."""
    import json

    from chatsql.analysis.reports import analyze_run_directory, generate_decision_memo

    if not run_dir.exists():
        typer.echo(f"Run directory not found: {run_dir}")
        raise typer.Exit(code=1)

    summary_file = run_dir / "error_analysis" / "summary.json"
    if summary_file.exists():
        with summary_file.open("r", encoding="utf-8") as f:
            summary = json.load(f)
    else:
        summary = analyze_run_directory(run_dir)

    memo = generate_decision_memo(summary, baseline_name=baseline)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(memo, encoding="utf-8")
        typer.echo(f"Exit Gate decision memo saved to: {output}")
    else:
        typer.echo(memo)


app.add_typer(benchmark_app, name="benchmark")
app.add_typer(experiment_app, name="experiment")
app.add_typer(analysis_app, name="analysis")

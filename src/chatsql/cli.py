from pathlib import Path
from typing import Annotated

import typer

from chatsql import __version__
from chatsql.benchmarks.bird import BirdLoader, BirdPaths, BirdValidator

app = typer.Typer(help="CHATSQL research harness.")
benchmark_app = typer.Typer(help="Benchmark utilities.")


@app.callback(invoke_without_command=True)
def main(
    version: bool = typer.Option(False, "--version", help="Show the CHATSQL version."),
) -> None:
    if version:
        typer.echo(__version__)
        raise typer.Exit()


@benchmark_app.command("validate")
def validate_benchmark(
    benchmark: Annotated[
        str,
        typer.Option(
            "--benchmark",
            help="Benchmark identifier to validate.",
        ),
    ] = "bird_mini_dev_sqlite_select_500",
    repo_root: Annotated[
        Path | None,
        typer.Option(
            "--repo-root",
            help="Repository root. Defaults to auto-detection.",
        ),
    ] = None,
    skip_catalogs: Annotated[
        bool,
        typer.Option(
            "--skip-catalogs",
            help="Skip SQLite catalog introspection.",
        ),
    ] = False,
) -> None:
    supported = {
        "bird_mini_dev_sqlite_select_500",
    }
    if benchmark not in supported:
        raise typer.BadParameter("supported benchmark identifiers: bird_mini_dev_sqlite_select_500")

    paths = BirdPaths.from_repo_root(repo_root)
    loader = BirdLoader(paths)
    try:
        cases, golds = loader.load_from_split("mini_dev_sqlite", select_only=True)
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


app.add_typer(benchmark_app, name="benchmark")

import typer

from chatsql import __version__

app = typer.Typer(help="CHATSQL research harness.")


@app.callback()
def main(
    version: bool = typer.Option(False, "--version", help="Show the CHATSQL version."),
) -> None:
    if version:
        typer.echo(__version__)
        raise typer.Exit()

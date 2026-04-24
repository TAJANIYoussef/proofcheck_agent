"""CLI entrypoint — typer + rich.

Commands:
  verify   <file.tex>          Run the full pipeline on a LaTeX file.
  resume   <session-id>        Resume an existing session's interactive review.
  report   <session-id>        Re-export the report for a saved session.
  notation show                List all symbols in the notation registry.
  notation add                 Register a new symbol.
  notation remove              Remove a symbol from the registry.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from deriv_verifier.config import settings

app = typer.Typer(
    name="deriv-verifier",
    help="Step-by-step LaTeX derivation verifier using local LLMs via Ollama.",
    add_completion=False,
)
notation_app = typer.Typer(help="Manage the notation registry.")
app.add_typer(notation_app, name="notation")

console = Console()
err_console = Console(stderr=True)


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------


@app.command()
def verify(
    file: Path = typer.Argument(..., help="Path to the .tex file to verify."),
    context: Optional[Path] = typer.Option(
        None, "--context", "-c", help="Optional paper draft .tex for notation context."
    ),
    notation: Optional[Path] = typer.Option(
        None, "--notation", "-n", help="Path to notation.yaml registry."
    ),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Output path for the Markdown report."
    ),
    non_interactive: bool = typer.Option(
        False, "--non-interactive", help="Skip the interactive review loop."
    ),
) -> None:
    """Verify a LaTeX derivation step-by-step."""
    _setup_logging()

    if not file.exists():
        err_console.print(f"[red]Error:[/red] File not found: {file}")
        raise typer.Exit(code=1)

    if not file.suffix == ".tex":
        err_console.print(f"[yellow]Warning:[/yellow] Expected a .tex file, got: {file}")

    from deriv_verifier.pipeline import run_pipeline_sync

    try:
        report = run_pipeline_sync(
            source_file=file,
            context_file=context,
            notation_file=notation,
            output_file=output,
            non_interactive=non_interactive,
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]Verification interrupted by user.[/yellow]")
        raise typer.Exit(code=0)
    except Exception as exc:
        err_console.print(f"[red]Pipeline error:[/red] {exc}")
        logger = logging.getLogger(__name__)
        logger.exception("Pipeline error")
        raise typer.Exit(code=2)

    # Final summary
    console.print()
    if report.has_critical_issues:
        console.print(
            f"[bold red]⚠ {report.invalid_count} INVALID step(s) detected.[/bold red]"
        )
    else:
        console.print("[bold green]Verification complete — no invalid steps.[/bold green]")
    console.print(
        f"[dim]Session ID: {report.session_id} | "
        f"Steps: {report.total_steps} valid={report.valid_count} "
        f"weak={report.weak_count} invalid={report.invalid_count}[/dim]"
    )


# ---------------------------------------------------------------------------
# resume
# ---------------------------------------------------------------------------


@app.command()
def resume(
    session_id: str = typer.Argument(..., help="Session ID to resume."),
) -> None:
    """Resume the interactive review for an existing session."""
    _setup_logging()
    from deriv_verifier.loop.interactive import run_interactive_loop
    from deriv_verifier.pipeline import _save_session, load_session

    try:
        report = load_session(session_id)
    except FileNotFoundError as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1)

    report = run_interactive_loop(report)
    _save_session(report, session_id)
    console.print(f"[green]Session {session_id} saved.[/green]")


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------


@app.command()
def report(
    session_id: str = typer.Argument(..., help="Session ID to export."),
    format: str = typer.Option("md", "--format", "-f", help="Output format: md or pdf."),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file path."),
) -> None:
    """Re-export the report for a saved session."""
    _setup_logging()
    from deriv_verifier.pipeline import load_session
    from deriv_verifier.tools.report_builder import write_markdown, write_pdf

    try:
        saved_report = load_session(session_id)
    except FileNotFoundError as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1)

    stem = Path(saved_report.source_file).stem
    if format.lower() == "pdf":
        out = output or Path(f"{stem}_{session_id}_report.pdf")
        try:
            write_pdf(saved_report, out)
            console.print(f"[green]PDF report written to {out}[/green]")
        except ImportError as exc:
            err_console.print(f"[red]PDF export unavailable:[/red] {exc}")
            raise typer.Exit(code=1)
    else:
        out = output or Path(f"{stem}_{session_id}_report.md")
        write_markdown(saved_report, out)
        console.print(f"[green]Markdown report written to {out}[/green]")


# ---------------------------------------------------------------------------
# notation subcommands
# ---------------------------------------------------------------------------


@notation_app.command("show")
def notation_show(
    notation_file: Path = typer.Option(
        Path("notation.yaml"), "--file", "-f", help="Path to notation.yaml."
    ),
    filter_symbol: Optional[str] = typer.Option(
        None, "--filter", help="Filter by symbol (substring match)."
    ),
) -> None:
    """List all symbols in the notation registry."""
    from deriv_verifier.tools.notation_registry import NotationRegistry

    registry = NotationRegistry.from_yaml(notation_file)
    if len(registry) == 0:
        console.print("[dim]Registry is empty.[/dim]")
        return

    table = Table(title=f"Notation Registry — {notation_file}", show_lines=True)
    table.add_column("Symbol", style="cyan")
    table.add_column("Type")
    table.add_column("Space")
    table.add_column("Assumptions")
    table.add_column("Defined at")

    for entry in sorted(registry.all_entries(), key=lambda e: e.symbol):
        if filter_symbol and filter_symbol not in entry.symbol:
            continue
        table.add_row(
            entry.symbol,
            entry.type.value,
            entry.space or "",
            ", ".join(entry.assumptions),
            entry.first_defined_at or "",
        )
    console.print(table)


@notation_app.command("add")
def notation_add(
    symbol: str = typer.Option(..., "--symbol", "-s", help=r"LaTeX symbol, e.g. \mu"),
    type_: str = typer.Option(..., "--type", "-t", help="Type: scalar|vector|measure|function|…"),
    space: Optional[str] = typer.Option(None, "--space", help="Mathematical space."),
    assumptions: Optional[str] = typer.Option(
        None, "--assumptions", help="Comma-separated list of assumptions."
    ),
    first_defined_at: Optional[str] = typer.Option(None, "--defined-at"),
    description: Optional[str] = typer.Option(None, "--description"),
    notation_file: Path = typer.Option(Path("notation.yaml"), "--file", "-f"),
) -> None:
    """Register a new symbol in the notation registry."""
    from deriv_verifier.schemas import NotationType
    from deriv_verifier.tools.notation_registry import NotationRegistry

    try:
        nt = NotationType(type_)
    except ValueError:
        err_console.print(
            f"[red]Unknown type '{type_}'. Valid: {[t.value for t in NotationType]}[/red]"
        )
        raise typer.Exit(code=1)

    registry = NotationRegistry.from_yaml(notation_file)
    assumption_list = [a.strip() for a in assumptions.split(",")] if assumptions else []
    registry.register(
        symbol,
        nt,
        space=space,
        assumptions=assumption_list,
        first_defined_at=first_defined_at,
        description=description,
        overwrite=True,
    )
    registry.to_yaml(notation_file)
    console.print(f"[green]Symbol '{symbol}' registered in {notation_file}.[/green]")


@notation_app.command("remove")
def notation_remove(
    symbol: str = typer.Option(..., "--symbol", "-s", help="LaTeX symbol to remove."),
    notation_file: Path = typer.Option(Path("notation.yaml"), "--file", "-f"),
) -> None:
    """Remove a symbol from the notation registry."""
    from deriv_verifier.tools.notation_registry import NotationRegistry

    registry = NotationRegistry.from_yaml(notation_file)
    removed = registry.remove(symbol)
    if removed:
        registry.to_yaml(notation_file)
        console.print(f"[green]Symbol '{symbol}' removed.[/green]")
    else:
        console.print(f"[yellow]Symbol '{symbol}' was not in the registry.[/yellow]")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_logging() -> None:
    settings.configure_logging()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app()

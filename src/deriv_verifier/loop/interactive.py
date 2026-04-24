"""Interactive per-step accept / reject / refine prompt.

Uses ``rich`` for coloured tables and prompts.  Only this module and
``cli.py`` are allowed to print to stdout.
"""

from __future__ import annotations

import logging
from typing import Literal

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from deriv_verifier.schemas import StepRecord, VerificationReport

logger = logging.getLogger(__name__)
console = Console()


# ---------------------------------------------------------------------------
# Status styling
# ---------------------------------------------------------------------------

_STATUS_STYLE: dict[str, str] = {
    "valid": "bold green",
    "weak": "bold yellow",
    "invalid": "bold red",
    "unchecked": "dim",
}

_STATUS_ICON: dict[str, str] = {
    "valid": "✅",
    "weak": "⚠️ ",
    "invalid": "❌",
    "unchecked": "⬜",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_interactive_loop(report: VerificationReport) -> VerificationReport:
    """Present each flagged step to the user and collect their decision.

    Steps with status ``valid`` are shown briefly and auto-accepted unless
    the user opts into reviewing them.  Steps with ``weak`` or ``invalid``
    always pause for user input.

    Returns the updated *report* with ``user_decision`` fields populated.
    """
    console.print()
    console.rule("[bold cyan]Derivation Verifier — Interactive Review[/bold cyan]")
    console.print(
        f"[dim]Session:[/dim] {report.session_id}  "
        f"[dim]File:[/dim] {report.source_file}  "
        f"[dim]Model:[/dim] {report.model_used}"
    )
    _print_summary_table(report)
    console.print()

    for step in report.steps:
        if step.status == "valid":
            _print_step_brief(step)
            step.user_decision = "accepted"
        else:
            decision = _review_step(step)
            step.user_decision = decision

    report.recount()
    console.print()
    console.rule("[bold cyan]Review complete[/bold cyan]")
    _print_summary_table(report)
    return report


def print_step_record(step: StepRecord) -> None:
    """Print a single step record (used in non-interactive report display)."""
    _print_step_detail(step)


# ---------------------------------------------------------------------------
# Summary table
# ---------------------------------------------------------------------------


def _print_summary_table(report: VerificationReport) -> None:
    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
    table.add_column("Steps", justify="right")
    table.add_column("✅ Valid", justify="right", style="green")
    table.add_column("⚠️  Weak", justify="right", style="yellow")
    table.add_column("❌ Invalid", justify="right", style="red")
    table.add_column("⬜ Unchecked", justify="right", style="dim")
    table.add_row(
        str(report.total_steps),
        str(report.valid_count),
        str(report.weak_count),
        str(report.invalid_count),
        str(report.unchecked_count),
    )
    console.print(table)


# ---------------------------------------------------------------------------
# Per-step display
# ---------------------------------------------------------------------------


def _print_step_brief(step: StepRecord) -> None:
    icon = _STATUS_ICON.get(step.status, "")
    style = _STATUS_STYLE.get(step.status, "")
    console.print(
        f"  {icon} [dim]Step {step.id}:[/dim] [{style}]{step.status.upper()}[/{style}]"
        f"  {step.claim[:80]}"
    )


def _print_step_detail(step: StepRecord) -> None:
    icon = _STATUS_ICON.get(step.status, "")
    style = _STATUS_STYLE.get(step.status, "")
    title = f"{icon} Step {step.id} — [{style}]{step.status.upper()}[/{style}]"
    body_lines: list[str] = [
        f"[bold]Claim:[/bold] {step.claim}",
        f"[bold]Confidence:[/bold] {step.confidence:.0%}   "
        f"[bold]CoVe rounds:[/bold] {step.cove_rounds}",
        "",
        f"[bold]LaTeX:[/bold]",
        f"[dim]{step.raw_latex}[/dim]",
        "",
        f"[bold]Reason:[/bold] {step.reason or '(none)'}",
    ]

    if step.missing_assumptions:
        body_lines.append("")
        body_lines.append("[bold yellow]Missing assumptions:[/bold yellow]")
        for a in step.missing_assumptions:
            body_lines.append(f"  • {a}")

    if step.hand_wave_flags:
        body_lines.append("")
        body_lines.append("[bold yellow]Hand-wave flags:[/bold yellow]")
        for f in step.hand_wave_flags:
            body_lines.append(f"  • {f}")

    if step.notation_issues:
        body_lines.append("")
        body_lines.append("[bold yellow]Notation issues:[/bold yellow]")
        for n in step.notation_issues:
            body_lines.append(f"  • {n}")

    if step.suggested_lemma:
        body_lines.append("")
        body_lines.append(f"[bold green]Suggested lemma:[/bold green] {step.suggested_lemma}")

    if step.suggested_rewrite:
        body_lines.append("")
        body_lines.append("[bold green]Suggested rewrite:[/bold green]")
        body_lines.append(f"[dim]{step.suggested_rewrite}[/dim]")

    if step.tools_called:
        body_lines.append("")
        body_lines.append(f"[dim]Tools: {', '.join(step.tools_called)}[/dim]")

    console.print(Panel("\n".join(body_lines), title=title, border_style=style or "white"))


# ---------------------------------------------------------------------------
# User decision prompt
# ---------------------------------------------------------------------------


def _review_step(
    step: StepRecord,
) -> Literal["accepted", "rejected", "refined", "pending"]:
    """Display step details and prompt user for a decision."""
    console.print()
    _print_step_detail(step)
    console.print()

    choices = "[A]ccept / [R]eject / [F]ix (refine) / [S]kip / [Q]uit"
    while True:
        raw = Prompt.ask(choices, default="S").strip().upper()
        if raw in ("A", "ACCEPT"):
            console.print("[green]Accepted.[/green]")
            return "accepted"
        elif raw in ("R", "REJECT"):
            console.print("[red]Rejected.[/red]")
            return "rejected"
        elif raw in ("F", "FIX", "REFINE"):
            _collect_refinement(step)
            return "refined"
        elif raw in ("S", "SKIP"):
            console.print("[dim]Skipped (pending).[/dim]")
            return "pending"
        elif raw in ("Q", "QUIT"):
            console.print("[bold red]Quitting review early.[/bold red]")
            raise KeyboardInterrupt
        else:
            console.print("[red]Unknown choice. Enter A / R / F / S / Q.[/red]")


def _collect_refinement(step: StepRecord) -> None:
    """Prompt user for a manual rewrite and store it on the step."""
    console.print("[dim]Enter your refined LaTeX (empty line to finish):[/dim]")
    lines: list[str] = []
    while True:
        line = input()
        if line == "":
            break
        lines.append(line)
    if lines:
        step.suggested_rewrite = "\n".join(lines)
        console.print("[green]Refinement saved.[/green]")
    else:
        console.print("[dim]No refinement provided.[/dim]")

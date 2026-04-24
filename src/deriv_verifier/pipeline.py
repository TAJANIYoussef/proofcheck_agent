"""Pipeline orchestrator: ties all stages together.

Stages:
  1. Parse     — LaTeX → DerivationBlock[]           (deterministic)
  2. Decompose — DerivationBlock[] → AtomicStep[]    (LLM)
  3. Verify    — AtomicStep[] → StepRecord[]         (LLM + tools, CoVe)
  4. Critique  — StepRecord[] → StepRecord[]         (LLM, weak/invalid only)
  5. Rewrite   — StepRecord[] → StepRecord[]         (LLM, weak/invalid only)
  6. Report    — StepRecord[] → VerificationReport

Supports both interactive and non-interactive modes.
Session state is saved to JSON between stages for resumability.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path

from deriv_verifier.agents import (
    critic as critic_agent,
    decomposer as decomposer_agent,
    rewriter as rewriter_agent,
)
from deriv_verifier.agents import parser as parser_agent
from deriv_verifier.agents import verifier as verifier_agent
from deriv_verifier.config import settings
from deriv_verifier.schemas import VerificationReport
from deriv_verifier.tools.assumption_stack import AssumptionStack
from deriv_verifier.tools.notation_registry import NotationRegistry
from deriv_verifier.tools.report_builder import write_markdown

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------


async def run_pipeline(
    source_file: str | Path,
    *,
    context_file: str | Path | None = None,
    notation_file: str | Path | None = None,
    output_file: str | Path | None = None,
    non_interactive: bool = False,
    session_id: str | None = None,
) -> VerificationReport:
    """Run the full verification pipeline on *source_file*.

    Parameters
    ----------
    source_file:
        Path to the ``.tex`` file containing the derivation to verify.
    context_file:
        Optional path to the full paper draft for notation context.
    notation_file:
        Optional path to a ``notation.yaml`` registry.
    output_file:
        Where to write the Markdown report.  Defaults to
        ``<source_stem>_report.md`` in the session directory.
    non_interactive:
        If True, skip the user review loop.
    session_id:
        Resume an existing session if provided; otherwise a new UUID is used.

    Returns
    -------
    VerificationReport
        Fully populated report after all pipeline stages.
    """
    source_file = Path(source_file)
    sid = session_id or str(uuid.uuid4())[:8]
    logger.info("Pipeline start — session=%s source=%s", sid, source_file)

    # --- Setup ---
    source = source_file.read_text(encoding="utf-8")
    context_source = (
        Path(context_file).read_text(encoding="utf-8") if context_file else ""
    )
    registry = (
        NotationRegistry.from_yaml(notation_file) if notation_file else NotationRegistry()
    )
    assumption_stack = AssumptionStack()

    # --- Stage 1: Parse ---
    logger.info("[1/5] Parsing LaTeX…")
    blocks = parser_agent.parse(source)

    # --- Stage 2: Decompose ---
    logger.info("[2/5] Decomposing into atomic steps…")
    steps = await decomposer_agent.decompose_blocks(blocks)

    # --- Stage 3: Verify ---
    logger.info("[3/5] Verifying steps (CoVe)…")
    records = await verifier_agent.verify_steps(
        steps,
        registry=registry,
        assumption_stack=assumption_stack,
        context_source=context_source,
    )

    # --- Stage 4: Critique ---
    logger.info("[4/5] Critiquing weak/invalid steps…")
    records = await critic_agent.critique_records(records)

    # --- Stage 5: Rewrite ---
    logger.info("[5/5] Generating rewrites…")
    records = await rewriter_agent.rewrite_records(records)

    # --- Build report ---
    report = VerificationReport(
        session_id=sid,
        source_file=str(source_file),
        model_used=settings.model_name,
        total_steps=len(records),
        steps=records,
        notation_registry_path=str(notation_file) if notation_file else None,
        context_file=str(context_file) if context_file else None,
    )
    report.recount()

    # --- Interactive loop (optional) ---
    if not non_interactive:
        from deriv_verifier.loop.interactive import run_interactive_loop
        report = run_interactive_loop(report)

    # --- Persist session ---
    _save_session(report, sid)

    # --- Write Markdown report ---
    out_path = output_file or (
        settings.session_dir / f"{source_file.stem}_{sid}_report.md"
    )
    write_markdown(report, out_path)
    logger.info("Report written to %s.", out_path)

    return report


def run_pipeline_sync(
    source_file: str | Path,
    **kwargs: object,
) -> VerificationReport:
    """Synchronous wrapper around :func:`run_pipeline`."""
    return asyncio.run(run_pipeline(source_file, **kwargs))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Session persistence
# ---------------------------------------------------------------------------


def _save_session(report: VerificationReport, session_id: str) -> Path:
    settings.session_dir.mkdir(parents=True, exist_ok=True)
    path = settings.session_dir / f"{session_id}.session.json"
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    logger.debug("Session saved to %s.", path)
    return path


def load_session(session_id: str) -> VerificationReport:
    """Load a previously saved session by ID."""
    path = settings.session_dir / f"{session_id}.session.json"
    if not path.exists():
        raise FileNotFoundError(f"No session found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return VerificationReport.model_validate(data)

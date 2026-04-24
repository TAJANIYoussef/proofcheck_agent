"""Rewriter agent: generate rigorous LaTeX rewrites and lemma citations.

Runs after the critic on steps that are still weak or invalid, producing
a polished suggested_rewrite and suggesting the canonical theorem that
closes the gap.
"""

from __future__ import annotations

import asyncio
import logging

from pydantic import BaseModel

from deriv_verifier.llm import MATH_PREAMBLE, make_agent
from deriv_verifier.schemas import StepRecord

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LLM response schema
# ---------------------------------------------------------------------------


class RewriteResult(BaseModel):
    """Structured output from the rewriter LLM call."""

    suggested_rewrite: str
    suggested_lemma: str | None = None
    explanation: str


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    MATH_PREAMBLE
    + """
Your current task: REWRITE.

You are given a mathematical step that has been flagged as weak or invalid.
Your job is to produce:
1. A rigorous LaTeX rewrite of the step that includes all missing hypotheses
   and references the correct theorem.
2. The name of the key theorem/lemma that justifies the step (e.g.
   "Dominated Convergence Theorem", "Fubini-Tonelli Theorem",
   "Banach-Alaoglu Theorem").
3. A brief explanation of what was missing and how the rewrite fixes it.

Rules:
- The rewrite must be valid LaTeX.
- State all required hypotheses explicitly.
- If the step is irreparably wrong (not just missing a hypothesis), say so
  in the explanation and provide the corrected version.
- Do not use vague language. Be precise.

Return a JSON object with:
  - suggested_rewrite: valid LaTeX string
  - suggested_lemma: theorem name (null if not applicable)
  - explanation: concise plain-text explanation
"""
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def rewrite_step(record: StepRecord) -> StepRecord:
    """Generate a rigorous rewrite for a weak or invalid *record*.

    Returns a new StepRecord with ``suggested_rewrite`` and
    ``suggested_lemma`` populated.  Valid/unchecked steps are returned
    unchanged.
    """
    if record.status not in ("weak", "invalid"):
        return record

    agent = make_agent(RewriteResult, _SYSTEM_PROMPT)
    user_msg = _build_user_msg(record)

    try:
        result = await agent.run(user_msg)
        data = result.output
        updated = record.model_copy(
            update={
                "suggested_rewrite": data.suggested_rewrite,
                "suggested_lemma": data.suggested_lemma or record.suggested_lemma,
                "reason": record.reason + f"\n[Rewriter] {data.explanation}",
                "tools_called": record.tools_called + ["rewriter"],
            }
        )
        logger.info(
            "Rewriter produced rewrite for step %d (lemma: %s).",
            record.id,
            data.suggested_lemma,
        )
        return updated
    except Exception as exc:  # noqa: BLE001
        logger.error("Rewriter failed on step %d: %s", record.id, exc)
        return record


async def rewrite_records(records: list[StepRecord]) -> list[StepRecord]:
    """Apply :func:`rewrite_step` to all *records* sequentially."""
    results: list[StepRecord] = []
    for record in records:
        results.append(await rewrite_step(record))
    return results


def rewrite_records_sync(records: list[StepRecord]) -> list[StepRecord]:
    return asyncio.run(rewrite_records(records))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_user_msg(record: StepRecord) -> str:
    return (
        f"Step {record.id}: {record.claim}\n\n"
        f"Status: {record.status}\n"
        f"Reason: {record.reason}\n\n"
        f"Original LaTeX:\n```latex\n{record.raw_latex}\n```\n\n"
        f"Missing assumptions: {record.missing_assumptions}\n"
        f"Hand-wave flags: {record.hand_wave_flags}\n"
        f"Notation issues: {record.notation_issues}\n\n"
        f"Current suggested lemma: {record.suggested_lemma or '(none)'}\n\n"
        "Produce a rigorous rewrite."
    )

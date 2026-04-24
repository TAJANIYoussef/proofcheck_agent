"""Critic agent: second-pass challenge of weak/invalid StepRecords.

The critic receives the verifier's output and actively tries to find
counter-arguments or confirm the weakness. It only runs on steps with
status "weak" or "invalid" to keep token usage low.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Literal

from pydantic import BaseModel

from deriv_verifier.llm import MATH_PREAMBLE, make_agent
from deriv_verifier.schemas import StepRecord

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LLM response schema
# ---------------------------------------------------------------------------


class CriticResult(BaseModel):
    """Structured output from the critic LLM call."""

    upheld_status: Literal["valid", "weak", "invalid"]
    critique: str
    additional_missing_assumptions: list[str]
    additional_notation_issues: list[str]
    updated_suggested_lemma: str | None = None
    updated_suggested_rewrite: str | None = None
    updated_confidence: float


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    MATH_PREAMBLE
    + """
Your current task: CRITIQUE.

You are a devil's advocate. The verifier has flagged a step as weak or invalid.
Your job:
1. Read the verifier's reason and decide whether it is correct.
2. If the verifier is too harsh (the step is actually valid), say so and provide
   justification.
3. If the verifier is too lenient (the step is even worse than flagged), escalate.
4. Add any missing assumptions or notation issues the verifier missed.
5. Refine the suggested lemma and rewrite if you can do better.

Return a JSON object with:
  - upheld_status: your final verdict ("valid" | "weak" | "invalid")
  - critique: a concise explanation of your decision
  - additional_missing_assumptions: list (empty if none)
  - additional_notation_issues: list (empty if none)
  - updated_suggested_lemma: null or string
  - updated_suggested_rewrite: null or string
  - updated_confidence: float 0.0–1.0
"""
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def critique_step(record: StepRecord) -> StepRecord:
    """Run the critic on a single *record* if it is weak or invalid.

    Returns a new StepRecord with updated fields.  Steps with status
    "valid" or "unchecked" are returned unchanged.
    """
    if record.status not in ("weak", "invalid"):
        return record

    agent = make_agent(CriticResult, _SYSTEM_PROMPT)
    user_msg = _build_user_msg(record)

    try:
        result = await agent.run(user_msg)
        data = result.output
        updated = record.model_copy(
            update={
                "status": data.upheld_status,
                "reason": record.reason + f"\n[Critic] {data.critique}",
                "missing_assumptions": list(
                    set(record.missing_assumptions + data.additional_missing_assumptions)
                ),
                "notation_issues": list(
                    set(record.notation_issues + data.additional_notation_issues)
                ),
                "suggested_lemma": data.updated_suggested_lemma or record.suggested_lemma,
                "suggested_rewrite": data.updated_suggested_rewrite or record.suggested_rewrite,
                "confidence": data.updated_confidence,
                "tools_called": record.tools_called + ["critic"],
            }
        )
        logger.info(
            "Critic on step %d: %s → %s (confidence=%.2f)",
            record.id,
            record.status,
            data.upheld_status,
            data.updated_confidence,
        )
        return updated
    except Exception as exc:  # noqa: BLE001
        logger.error("Critic failed on step %d: %s", record.id, exc)
        return record


async def critique_records(records: list[StepRecord]) -> list[StepRecord]:
    """Run the critic on all *records*, skipping valid/unchecked ones."""
    results: list[StepRecord] = []
    for record in records:
        results.append(await critique_step(record))
    return results


def critique_records_sync(records: list[StepRecord]) -> list[StepRecord]:
    return asyncio.run(critique_records(records))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_user_msg(record: StepRecord) -> str:
    return (
        f"Step {record.id}: {record.claim}\n\n"
        f"LaTeX: {record.raw_latex}\n\n"
        f"Justification given: {record.justification or '(none)'}\n\n"
        f"Verifier status: {record.status}\n"
        f"Verifier reason: {record.reason}\n\n"
        f"Missing assumptions flagged: {record.missing_assumptions}\n"
        f"Hand-wave flags: {record.hand_wave_flags}\n"
        f"Notation issues: {record.notation_issues}\n\n"
        f"Current suggested lemma: {record.suggested_lemma or '(none)'}\n"
        f"Current suggested rewrite:\n"
        f"```latex\n{record.suggested_rewrite or '(none)'}\n```\n\n"
        "Challenge or confirm this verdict."
    )

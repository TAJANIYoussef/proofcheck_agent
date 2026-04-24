"""Verifier agent: per-step CoVe (Chain-of-Verification) loop.

For each AtomicStep:
  1. Generate verification questions about the step's validity.
  2. Answer each question — preferring deterministic tools (SymPy, hand_wave,
     notation registry) where applicable, falling back to the LLM.
  3. Aggregate answers to decide status: valid / weak / invalid.
  4. Repeat up to ``settings.max_cove_rounds`` times if verdict is uncertain.
  5. Return a StepRecord.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Literal

from pydantic import BaseModel

from deriv_verifier.config import settings
from deriv_verifier.llm import MATH_PREAMBLE, make_agent
from deriv_verifier.schemas import (
    AtomicStep,
    CoveRound,
    StepRecord,
    VerificationAnswer,
    VerificationQuestion,
)
from deriv_verifier.tools.assumption_stack import AssumptionStack
from deriv_verifier.tools.hand_wave import detect_hand_waves, summarise_flags
from deriv_verifier.tools.notation_registry import NotationRegistry
from deriv_verifier.tools.sympy_check import check_equality

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LLM response schemas
# ---------------------------------------------------------------------------


class QuestionList(BaseModel):
    questions: list[VerificationQuestion]


class VerificationVerdict(BaseModel):
    status: Literal["valid", "weak", "invalid", "needs_another_round"]
    reason: str
    missing_assumptions: list[str]
    notation_issues: list[str]
    suggested_lemma: str | None = None
    suggested_rewrite: str | None = None
    confidence: float


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

_QUESTION_GEN_PROMPT = (
    MATH_PREAMBLE
    + """
Your current task: GENERATE VERIFICATION QUESTIONS.

Given an atomic step from a mathematical derivation, generate a list of
precise yes/no verification questions that must all be answered "yes" for
the step to be valid.

Focus on:
- Are all required hypotheses explicitly stated? (integrability, measurability, σ-finiteness)
- Is the theorem/lemma being applied actually applicable here?
- Is the notation consistent with prior definitions?
- Is there a missing regularity condition (compactness, continuity, boundedness)?
- Is any limit/integral interchange justified (DCT, MCT, Fubini/Tonelli hypothesis)?

Return a JSON object with a "questions" array.
Each question: {"question": "...", "tool_hint": "sympy_check|hand_wave|notation_registry|null"}
"""
)

_VERDICT_PROMPT = (
    MATH_PREAMBLE
    + """
Your current task: DELIVER VERDICT.

Given an atomic step and the answers to a set of verification questions,
decide whether the step is:
  - "valid": fully rigorous, all hypotheses present and correct
  - "weak": partially justified but missing at least one hypothesis or vague
  - "invalid": mathematically incorrect or unjustified
  - "needs_another_round": ambiguous — more verification needed

Return a JSON object with:
  - status
  - reason: concise explanation
  - missing_assumptions: list of strings (empty if none)
  - notation_issues: list of strings (empty if none)
  - suggested_lemma: theorem name that justifies or fixes the step (null if not applicable)
  - suggested_rewrite: rigorous LaTeX rewrite (null if step is valid)
  - confidence: float 0.0–1.0
"""
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def verify_step(
    step: AtomicStep,
    registry: NotationRegistry | None = None,
    assumption_stack: AssumptionStack | None = None,
    context_source: str = "",
) -> StepRecord:
    """Run the CoVe loop for a single *step* and return a :class:`StepRecord`."""
    registry = registry or NotationRegistry()
    assumption_stack = assumption_stack or AssumptionStack()

    record = StepRecord(
        id=step.id,
        raw_latex=step.raw_latex,
        claim=step.claim,
        justification=step.justification,
    )
    tools_called: list[str] = []
    cove_rounds: list[CoveRound] = []

    for round_num in range(1, settings.max_cove_rounds + 1):
        round_result = await _run_cove_round(
            round_num=round_num,
            step=step,
            record=record,
            registry=registry,
            assumption_stack=assumption_stack,
            context_source=context_source,
            tools_called=tools_called,
        )
        cove_rounds.append(round_result)

        if round_result.verdict != "needs_another_round":
            break

    # Merge last round's verdict into the record
    if cove_rounds:
        last = cove_rounds[-1]
        if last.verdict in ("valid", "weak", "invalid"):
            record = record.model_copy(update={"status": last.verdict})

    record = record.model_copy(
        update={
            "cove_rounds": len(cove_rounds),
            "tools_called": tools_called,
        }
    )
    logger.info("Step %d → %s (confidence=%.2f)", step.id, record.status, record.confidence)
    return record


async def verify_steps(
    steps: list[AtomicStep],
    registry: NotationRegistry | None = None,
    assumption_stack: AssumptionStack | None = None,
    context_source: str = "",
) -> list[StepRecord]:
    """Verify all steps sequentially (preserves assumption stack ordering)."""
    records: list[StepRecord] = []
    for step in steps:
        record = await verify_step(
            step,
            registry=registry,
            assumption_stack=assumption_stack,
            context_source=context_source,
        )
        records.append(record)
    return records


def verify_steps_sync(
    steps: list[AtomicStep],
    registry: NotationRegistry | None = None,
    assumption_stack: AssumptionStack | None = None,
    context_source: str = "",
) -> list[StepRecord]:
    return asyncio.run(
        verify_steps(steps, registry=registry, assumption_stack=assumption_stack,
                     context_source=context_source)
    )


# ---------------------------------------------------------------------------
# CoVe inner loop
# ---------------------------------------------------------------------------


async def _run_cove_round(
    *,
    round_num: int,
    step: AtomicStep,
    record: StepRecord,
    registry: NotationRegistry,
    assumption_stack: AssumptionStack,
    context_source: str,
    tools_called: list[str],
) -> CoveRound:
    # Step 1: deterministic pre-checks (no LLM)
    pre_flags = _deterministic_checks(step, record, registry, context_source, tools_called)

    # Step 2: generate verification questions via LLM
    questions = await _generate_questions(step, record)

    # Step 3: answer questions (tools first, then LLM fallback)
    answers = await _answer_questions(
        questions, step, record, registry, assumption_stack, tools_called
    )

    # Step 4: verdict via LLM
    verdict_obj = await _get_verdict(step, record, answers, pre_flags)

    # Merge verdict fields into the mutable record copy
    record.__dict__.update(
        {
            "status": verdict_obj.status if verdict_obj.status != "needs_another_round"
                      else record.status,
            "reason": verdict_obj.reason,
            "missing_assumptions": list(
                set(record.missing_assumptions + verdict_obj.missing_assumptions)
            ),
            "notation_issues": list(
                set(record.notation_issues + verdict_obj.notation_issues)
            ),
            "suggested_lemma": verdict_obj.suggested_lemma or record.suggested_lemma,
            "suggested_rewrite": verdict_obj.suggested_rewrite or record.suggested_rewrite,
            "confidence": verdict_obj.confidence,
        }
    )

    return CoveRound(
        round_number=round_num,
        questions=questions,
        answers=answers,
        verdict=verdict_obj.status,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# Deterministic pre-checks (no LLM)
# ---------------------------------------------------------------------------


def _deterministic_checks(
    step: AtomicStep,
    record: StepRecord,
    registry: NotationRegistry,
    context_source: str,
    tools_called: list[str],
) -> list[str]:
    """Run all deterministic checks and return a list of pre-flag strings."""
    pre_flags: list[str] = []

    # Hand-wave detection
    hw_flags = detect_hand_waves(step.raw_latex + " " + step.claim)
    if hw_flags:
        tools_called.append("hand_wave")
        summaries = summarise_flags(hw_flags)
        record.hand_wave_flags.extend(summaries)
        pre_flags.extend(summaries)

    # Notation conflict check
    unregistered = registry.conflict_check(step.raw_latex)
    if unregistered:
        tools_called.append("notation_registry")
        for sym in unregistered:
            issue = f"Symbol '{sym}' used but not registered in notation registry"
            record.notation_issues.append(issue)
            pre_flags.append(issue)

    return pre_flags


# ---------------------------------------------------------------------------
# LLM calls
# ---------------------------------------------------------------------------


async def _generate_questions(step: AtomicStep, record: StepRecord) -> list[VerificationQuestion]:
    agent = make_agent(QuestionList, _QUESTION_GEN_PROMPT)
    user_msg = (
        f"Step {step.id}: {step.claim}\n\n"
        f"LaTeX: {step.raw_latex}\n\n"
        f"Justification given: {step.justification or '(none)'}\n\n"
        f"Pre-detected issues: {record.hand_wave_flags + record.notation_issues}\n\n"
        "Generate verification questions."
    )
    try:
        result = await agent.run(user_msg)
        return result.output.questions
    except Exception as exc:  # noqa: BLE001
        logger.warning("Question generation failed for step %d: %s", step.id, exc)
        return []


async def _answer_questions(
    questions: list[VerificationQuestion],
    step: AtomicStep,
    record: StepRecord,
    registry: NotationRegistry,
    assumption_stack: AssumptionStack,
    tools_called: list[str],
) -> list[VerificationAnswer]:
    answers: list[VerificationAnswer] = []
    for q in questions:
        answer = await _answer_one(q, step, registry, assumption_stack, tools_called)
        answers.append(answer)
    return answers


async def _answer_one(
    question: VerificationQuestion,
    step: AtomicStep,
    registry: NotationRegistry,
    assumption_stack: AssumptionStack,
    tools_called: list[str],
) -> VerificationAnswer:
    """Try deterministic tools first; fall back to returning unanswered."""
    hint = question.tool_hint

    if hint == "sympy_check":
        tools_called.append("sympy_check")
        # Best-effort: try to check lhs=rhs from the raw_latex
        parts = step.raw_latex.split("=", 1)
        if len(parts) == 2:
            result = check_equality(parts[0].strip(), parts[1].strip())
            return VerificationAnswer(
                question=question.question,
                answer=result.reason,
                tool_used="sympy_check",
                passed=result.passed,
            )

    if hint == "notation_registry":
        tools_called.append("notation_registry")
        unregistered = registry.conflict_check(step.raw_latex)
        passed = len(unregistered) == 0
        answer_text = (
            "All symbols registered." if passed
            else f"Unregistered: {unregistered}"
        )
        return VerificationAnswer(
            question=question.question,
            answer=answer_text,
            tool_used="notation_registry",
            passed=passed,
        )

    # Default: unanswered (LLM will factor in what it knows)
    return VerificationAnswer(
        question=question.question,
        answer="Requires LLM assessment.",
        tool_used=None,
        passed=True,  # optimistic default; verdict LLM will decide
    )


async def _get_verdict(
    step: AtomicStep,
    record: StepRecord,
    answers: list[VerificationAnswer],
    pre_flags: list[str],
) -> VerificationVerdict:
    agent = make_agent(VerificationVerdict, _VERDICT_PROMPT)
    answers_text = "\n".join(
        f"Q: {a.question}\nA: {a.answer} [passed={a.passed}]" for a in answers
    )
    user_msg = (
        f"Step {step.id}: {step.claim}\n\n"
        f"LaTeX: {step.raw_latex}\n\n"
        f"Justification: {step.justification or '(none)'}\n\n"
        f"Pre-detected issues:\n{chr(10).join(pre_flags) or '(none)'}\n\n"
        f"Verification Q&A:\n{answers_text or '(none)'}\n\n"
        "Deliver your verdict."
    )
    try:
        result = await agent.run(user_msg)
        return result.output
    except Exception as exc:  # noqa: BLE001
        logger.error("Verdict generation failed for step %d: %s", step.id, exc)
        return VerificationVerdict(
            status="weak",
            reason=f"LLM verdict failed: {exc}",
            missing_assumptions=[],
            notation_issues=[],
            confidence=0.0,
        )

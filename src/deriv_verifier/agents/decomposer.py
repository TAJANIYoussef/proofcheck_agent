"""Decomposer agent: DerivationBlock list → list[AtomicStep] via LLM.

Each block is submitted to the LLM with a prompt that asks it to identify
every distinct logical move and return them as a structured list of
AtomicStep objects.
"""

from __future__ import annotations

import asyncio
import logging

from pydantic import BaseModel

from deriv_verifier.llm import MATH_PREAMBLE, make_agent
from deriv_verifier.schemas import AtomicStep, DerivationBlock

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LLM response schema
# ---------------------------------------------------------------------------


class DecompositionResult(BaseModel):
    """Structured output from the decomposer LLM call."""

    steps: list[AtomicStep]


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    MATH_PREAMBLE
    + """
Your current task: DECOMPOSE.

Given a LaTeX block, identify every distinct atomic logical step.
An atomic step is a single mathematical move: one substitution, one limit,
one application of a theorem, one algebraic manipulation, etc.

For each step output:
- id: sequential integer starting from the offset provided
- source_block_index: the block index given to you
- raw_latex: the exact LaTeX fragment for this step
- claim: a precise natural-language description of what this step asserts
- justification: what the author wrote to justify it (null if implicit)

Return a JSON object with a "steps" array. Preserve the mathematical content
exactly. Do not invent steps that are not present.
"""
)


def _user_prompt(block: DerivationBlock, id_offset: int) -> str:
    return (
        f"Block index: {block.index}\n"
        f"Block kind: {block.kind.value}\n"
        f"Step ID offset (first step gets id={id_offset + 1}): {id_offset}\n\n"
        f"LaTeX:\n```latex\n{block.raw_latex}\n```\n\n"
        "Decompose this block into atomic steps and return the JSON."
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def decompose_blocks(blocks: list[DerivationBlock]) -> list[AtomicStep]:
    """Decompose all *blocks* into atomic steps via LLM.

    Processes each block sequentially to maintain correct step IDs.
    """
    agent = make_agent(DecompositionResult, _SYSTEM_PROMPT)
    all_steps: list[AtomicStep] = []

    for block in blocks:
        id_offset = len(all_steps)
        prompt = _user_prompt(block, id_offset)
        try:
            result = await agent.run(prompt)
            # Re-assign IDs to ensure they are globally sequential
            for i, step in enumerate(result.output.steps):
                step = step.model_copy(update={"id": id_offset + i + 1})
                all_steps.append(step)
            logger.debug(
                "Block %d → %d step(s).", block.index, len(result.output.steps)
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Decomposer failed on block %d: %s", block.index, exc)
            # Insert a placeholder step so downstream stages still get a record
            all_steps.append(
                AtomicStep(
                    id=id_offset + 1,
                    source_block_index=block.index,
                    raw_latex=block.raw_latex[:200],
                    claim="(decomposition failed — see logs)",
                    justification=None,
                )
            )

    logger.info("Decomposer produced %d atomic step(s) total.", len(all_steps))
    return all_steps


def decompose_blocks_sync(blocks: list[DerivationBlock]) -> list[AtomicStep]:
    """Synchronous wrapper around :func:`decompose_blocks`."""
    return asyncio.run(decompose_blocks(blocks))

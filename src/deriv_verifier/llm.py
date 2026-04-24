"""PydanticAI Agent factory bound to the Ollama OpenAI-compatible endpoint.

All LLM interaction flows through this module.  The rest of the codebase
never imports ``openai`` or ``pydantic_ai`` directly — they call
``make_agent`` and ``make_client`` from here.

Switch models at runtime by setting ``MODEL_NAME`` in ``.env``.
"""

from __future__ import annotations

import logging
from typing import Any, TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from deriv_verifier.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


# ---------------------------------------------------------------------------
# Low-level client
# ---------------------------------------------------------------------------


def make_client() -> AsyncOpenAI:
    """Return an AsyncOpenAI client pointing at the Ollama endpoint."""
    return AsyncOpenAI(
        base_url=settings.openai_base_url,
        api_key="ollama",  # Ollama ignores the key but AsyncOpenAI requires one
    )


# ---------------------------------------------------------------------------
# PydanticAI model wrapper
# ---------------------------------------------------------------------------


def make_openai_model() -> OpenAIChatModel:
    """Return a PydanticAI OpenAIChatModel configured for the local Ollama server.

    PydanticAI ≥1.x separates transport config (OpenAIProvider) from model
    identity (OpenAIChatModel); base_url and api_key live on the provider.
    """
    provider = OpenAIProvider(
        base_url=settings.openai_base_url,
        api_key="ollama",  # Ollama ignores the key; value required by openai SDK
    )
    return OpenAIChatModel(model_name=settings.model_name, provider=provider)


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------


def make_agent(
    result_type: type[T],
    system_prompt: str,
    *,
    model: OpenAIChatModel | None = None,
    retries: int = 2,
    **agent_kwargs: Any,
) -> Agent[T]:
    """Create a PydanticAI ``Agent`` with structured output.

    Parameters
    ----------
    result_type:
        Pydantic model class that the agent must return.
    system_prompt:
        Instruction text sent as the system role message.
    model:
        Optional pre-built ``OpenAIChatModel``; defaults to ``make_openai_model()``.
    retries:
        Number of automatic retries on validation failure.
    **agent_kwargs:
        Forwarded verbatim to ``pydantic_ai.Agent``.

    Returns
    -------
    Agent[T]
        Configured agent ready to call with ``.run(user_prompt)``.
    """
    resolved_model = model or make_openai_model()
    logger.debug(
        "Creating Agent(output_type=%s, model=%s)",
        result_type.__name__,
        settings.model_name,
    )
    return Agent(
        model=resolved_model,
        output_type=result_type,
        system_prompt=system_prompt,
        retries=retries,
        **agent_kwargs,
    )


# ---------------------------------------------------------------------------
# Shared math-domain system prompt preamble
# ---------------------------------------------------------------------------

MATH_PREAMBLE = """\
You are a rigorous mathematical proof assistant specialising in:
- Measure theory and integration
- Stochastic processes and probability
- Optimal transport and Sinkhorn divergences
- Functional analysis and convex duality

Your task is to verify derivations written in LaTeX with PhD-level rigour.
You must identify every implicit assumption, unjustified step, and notation
inconsistency. Be precise: cite theorems by name when suggesting fixes.
Never use vague language ("clearly", "obviously", "it follows that").
Always output valid JSON matching the requested schema.
"""

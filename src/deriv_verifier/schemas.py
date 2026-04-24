"""Core Pydantic models shared across all pipeline stages."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class BlockKind(str, Enum):
    EQUATION = "equation"
    TEXT = "text"
    PROOF = "proof"
    THEOREM = "theorem"
    LEMMA = "lemma"
    DEFINITION = "definition"
    REMARK = "remark"
    ASSUMPTION = "assumption"
    OTHER = "other"


class NotationType(str, Enum):
    SCALAR = "scalar"
    VECTOR = "vector"
    MATRIX = "matrix"
    FUNCTION = "function"
    MEASURE = "measure"
    OPERATOR = "operator"
    SET = "set"
    SPACE = "space"
    OTHER = "other"


# ---------------------------------------------------------------------------
# Notation registry entry
# ---------------------------------------------------------------------------


class NotationEntry(BaseModel):
    """One symbol in the notation registry (notation.yaml)."""

    symbol: str = Field(..., description="Raw LaTeX symbol, e.g. r'\\mu'")
    type: NotationType
    space: str | None = Field(
        default=None,
        description="Mathematical space or type, e.g. r'\\mathcal{M}(X)'",
    )
    assumptions: list[str] = Field(
        default_factory=list,
        description="Active assumptions, e.g. ['sigma-finite', 'Borel']",
    )
    first_defined_at: str | None = Field(
        default=None,
        description="Section/line reference where the symbol is first defined",
    )
    description: str | None = Field(default=None, description="Free-text description")


# ---------------------------------------------------------------------------
# Derivation block (output of the LaTeX parser)
# ---------------------------------------------------------------------------


class DerivationBlock(BaseModel):
    """A contiguous chunk of LaTeX with a semantic type."""

    index: int = Field(..., description="0-based position in the document")
    kind: BlockKind
    raw_latex: str = Field(..., description="Original LaTeX text for this block")
    environment: str | None = Field(
        default=None,
        description="LaTeX environment name if kind != TEXT, e.g. 'align*'",
    )


# ---------------------------------------------------------------------------
# Atomic step (output of the decomposer)
# ---------------------------------------------------------------------------


class AtomicStep(BaseModel):
    """One logical move extracted from a DerivationBlock."""

    id: int = Field(..., ge=1, description="1-indexed position in the derivation")
    source_block_index: int = Field(
        ..., description="Index of the DerivationBlock this step came from"
    )
    raw_latex: str = Field(..., description="LaTeX fragment for this step")
    claim: str = Field(..., description="Natural-language restatement of the step")
    justification: str | None = Field(
        default=None,
        description="What the author wrote to justify the move (if any)",
    )


# ---------------------------------------------------------------------------
# Per-step verification record (core data object)
# ---------------------------------------------------------------------------


class StepRecord(BaseModel):
    """Full verification record for one atomic step."""

    id: int = Field(..., ge=1)
    raw_latex: str
    claim: str
    justification: str | None = None
    status: Literal["valid", "weak", "invalid", "unchecked"] = "unchecked"
    reason: str = Field(default="", description="Why this status was assigned")
    missing_assumptions: list[str] = Field(default_factory=list)
    hand_wave_flags: list[str] = Field(default_factory=list)
    notation_issues: list[str] = Field(default_factory=list)
    suggested_rewrite: str | None = None
    suggested_lemma: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    cove_rounds: int = Field(default=0, ge=0)
    tools_called: list[str] = Field(default_factory=list)
    user_decision: Literal["pending", "accepted", "rejected", "refined"] = "pending"

    @field_validator("confidence")
    @classmethod
    def round_confidence(cls, v: float) -> float:
        return round(v, 4)


# ---------------------------------------------------------------------------
# Verification report (output of the full pipeline)
# ---------------------------------------------------------------------------


class VerificationReport(BaseModel):
    """Aggregated result for an entire derivation."""

    session_id: str = Field(..., description="UUID identifying this verification run")
    source_file: str = Field(..., description="Path to the input .tex file")
    model_used: str
    total_steps: int
    valid_count: int = 0
    weak_count: int = 0
    invalid_count: int = 0
    unchecked_count: int = 0
    steps: list[StepRecord] = Field(default_factory=list)
    notation_registry_path: str | None = None
    context_file: str | None = None
    summary: str = Field(default="", description="LLM-generated overall summary")

    @property
    def has_critical_issues(self) -> bool:
        return self.invalid_count > 0

    def recount(self) -> None:
        """Recompute status counters from the steps list."""
        self.valid_count = sum(1 for s in self.steps if s.status == "valid")
        self.weak_count = sum(1 for s in self.steps if s.status == "weak")
        self.invalid_count = sum(1 for s in self.steps if s.status == "invalid")
        self.unchecked_count = sum(1 for s in self.steps if s.status == "unchecked")
        self.total_steps = len(self.steps)


# ---------------------------------------------------------------------------
# CoVe (Chain-of-Verification) intermediate objects
# ---------------------------------------------------------------------------


class VerificationQuestion(BaseModel):
    """One verification question generated during a CoVe round."""

    question: str
    tool_hint: str | None = Field(
        default=None,
        description="Which tool to call to answer this question, if deterministic",
    )


class VerificationAnswer(BaseModel):
    """Answer to one CoVe question (tool result or LLM answer)."""

    question: str
    answer: str
    tool_used: str | None = None
    passed: bool = Field(
        ..., description="Does the answer support the step's validity?"
    )


class CoveRound(BaseModel):
    """One complete CoVe inner loop iteration for a single step."""

    round_number: int = Field(..., ge=1)
    questions: list[VerificationQuestion] = Field(default_factory=list)
    answers: list[VerificationAnswer] = Field(default_factory=list)
    verdict: Literal["valid", "weak", "invalid", "needs_another_round"]

"""Tests for src/deriv_verifier/schemas.py."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from deriv_verifier.schemas import (
    AtomicStep,
    BlockKind,
    CoveRound,
    DerivationBlock,
    NotationEntry,
    NotationType,
    StepRecord,
    VerificationQuestion,
    VerificationReport,
)


# ---------------------------------------------------------------------------
# NotationEntry
# ---------------------------------------------------------------------------


class TestNotationEntry:
    def test_minimal_construction(self) -> None:
        entry = NotationEntry(symbol=r"\mu", type=NotationType.MEASURE)
        assert entry.symbol == r"\mu"
        assert entry.space is None
        assert entry.assumptions == []

    def test_full_construction(self) -> None:
        entry = NotationEntry(
            symbol=r"\mu",
            type=NotationType.MEASURE,
            space=r"\mathcal{M}(X)",
            assumptions=["sigma-finite", "Borel"],
            first_defined_at="Section 2.1",
            description="Reference measure on X",
        )
        assert "sigma-finite" in entry.assumptions
        assert entry.first_defined_at == "Section 2.1"

    def test_round_trip_serialization(self) -> None:
        entry = NotationEntry(
            symbol=r"\pi",
            type=NotationType.MEASURE,
            assumptions=["coupling"],
        )
        data = entry.model_dump()
        restored = NotationEntry.model_validate(data)
        assert restored == entry


# ---------------------------------------------------------------------------
# DerivationBlock
# ---------------------------------------------------------------------------


class TestDerivationBlock:
    def test_text_block(self) -> None:
        block = DerivationBlock(index=0, kind=BlockKind.TEXT, raw_latex="Let $X$ be compact.")
        assert block.environment is None

    def test_equation_block(self) -> None:
        block = DerivationBlock(
            index=1,
            kind=BlockKind.EQUATION,
            raw_latex=r"\int f \, d\mu",
            environment="equation*",
        )
        assert block.environment == "equation*"

    def test_index_zero_allowed(self) -> None:
        block = DerivationBlock(index=0, kind=BlockKind.OTHER, raw_latex="x")
        assert block.index == 0


# ---------------------------------------------------------------------------
# AtomicStep
# ---------------------------------------------------------------------------


class TestAtomicStep:
    def test_id_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            AtomicStep(id=0, source_block_index=0, raw_latex="x", claim="x equals zero")

    def test_valid_step(self) -> None:
        step = AtomicStep(
            id=1,
            source_block_index=0,
            raw_latex=r"a + b = b + a",
            claim="Addition is commutative",
            justification="Axiom of real numbers",
        )
        assert step.justification == "Axiom of real numbers"

    def test_justification_optional(self) -> None:
        step = AtomicStep(
            id=2,
            source_block_index=1,
            raw_latex=r"f \in L^1(\mu)",
            claim="f is integrable",
        )
        assert step.justification is None


# ---------------------------------------------------------------------------
# StepRecord
# ---------------------------------------------------------------------------


class TestStepRecord:
    def _make_step(self, **kwargs: object) -> StepRecord:
        defaults: dict[str, object] = {
            "id": 1,
            "raw_latex": r"\int f \, d\mu < \infty",
            "claim": "f is integrable",
        }
        defaults.update(kwargs)
        return StepRecord.model_validate(defaults)

    def test_default_status_is_unchecked(self) -> None:
        step = self._make_step()
        assert step.status == "unchecked"

    def test_default_user_decision_is_pending(self) -> None:
        step = self._make_step()
        assert step.user_decision == "pending"

    def test_confidence_clamped_and_rounded(self) -> None:
        step = self._make_step(confidence=0.123456789)
        assert step.confidence == round(0.123456789, 4)

    def test_confidence_below_zero_fails(self) -> None:
        with pytest.raises(ValidationError):
            self._make_step(confidence=-0.1)

    def test_confidence_above_one_fails(self) -> None:
        with pytest.raises(ValidationError):
            self._make_step(confidence=1.001)

    def test_invalid_status_fails(self) -> None:
        with pytest.raises(ValidationError):
            self._make_step(status="maybe")

    def test_invalid_user_decision_fails(self) -> None:
        with pytest.raises(ValidationError):
            self._make_step(user_decision="ignored")

    def test_lists_default_empty(self) -> None:
        step = self._make_step()
        assert step.missing_assumptions == []
        assert step.hand_wave_flags == []
        assert step.notation_issues == []
        assert step.tools_called == []

    def test_full_record_round_trip(self) -> None:
        step = StepRecord(
            id=3,
            raw_latex=r"\lim_{n} \int f_n \, d\mu = \int f \, d\mu",
            claim="Limit and integral may be exchanged",
            status="weak",
            reason="Missing DCT hypothesis",
            missing_assumptions=["integrability of g dominating f_n"],
            hand_wave_flags=["unjustified limit-integral swap"],
            confidence=0.35,
            cove_rounds=2,
            tools_called=["sympy_check", "hand_wave"],
            user_decision="pending",
        )
        data = step.model_dump()
        restored = StepRecord.model_validate(data)
        assert restored == step


# ---------------------------------------------------------------------------
# VerificationReport
# ---------------------------------------------------------------------------


class TestVerificationReport:
    def _make_report(self, steps: list[StepRecord] | None = None) -> VerificationReport:
        return VerificationReport(
            session_id="test-session-001",
            source_file="derivation.tex",
            model_used="gpt-oss:20b",
            total_steps=0,
            steps=steps or [],
        )

    def test_has_critical_issues_false_when_no_invalid(self) -> None:
        report = self._make_report()
        assert not report.has_critical_issues

    def test_has_critical_issues_true_with_invalid_step(self) -> None:
        step = StepRecord(
            id=1,
            raw_latex="x",
            claim="x",
            status="invalid",
            reason="wrong",
        )
        report = self._make_report(steps=[step])
        report.recount()
        assert report.has_critical_issues
        assert report.invalid_count == 1

    def test_recount_updates_all_counters(self) -> None:
        steps = [
            StepRecord(id=1, raw_latex="a", claim="a", status="valid", reason="ok"),
            StepRecord(id=2, raw_latex="b", claim="b", status="weak", reason="meh"),
            StepRecord(id=3, raw_latex="c", claim="c", status="invalid", reason="bad"),
            StepRecord(id=4, raw_latex="d", claim="d", status="unchecked", reason=""),
        ]
        report = self._make_report(steps=steps)
        report.recount()
        assert report.valid_count == 1
        assert report.weak_count == 1
        assert report.invalid_count == 1
        assert report.unchecked_count == 1
        assert report.total_steps == 4


# ---------------------------------------------------------------------------
# CoveRound
# ---------------------------------------------------------------------------


class TestCoveRound:
    def test_construction(self) -> None:
        q = VerificationQuestion(
            question="Is the integrand bounded?", tool_hint="sympy_check"
        )
        round_ = CoveRound(
            round_number=1,
            questions=[q],
            answers=[],
            verdict="needs_another_round",
        )
        assert round_.round_number == 1
        assert round_.verdict == "needs_another_round"

    def test_invalid_verdict(self) -> None:
        with pytest.raises(ValidationError):
            CoveRound(round_number=1, verdict="uncertain")  # type: ignore[arg-type]

    def test_round_number_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            CoveRound(round_number=0, verdict="valid")  # type: ignore[arg-type]

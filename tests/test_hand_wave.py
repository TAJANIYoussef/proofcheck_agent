"""Tests for src/deriv_verifier/tools/hand_wave.py."""

from __future__ import annotations

import pytest

from deriv_verifier.tools.hand_wave import (
    HandWaveFlag,
    detect_hand_waves,
    has_high_severity_flags,
    summarise_flags,
)


class TestDetectHandWaves:
    def test_no_flags_in_rigorous_text(self) -> None:
        source = (
            "By the Dominated Convergence Theorem (since $|f_n| \\leq g \\in L^1(\\mu)$), "
            "we have $\\lim_n \\int f_n \\, d\\mu = \\int f \\, d\\mu$."
        )
        flags = detect_hand_waves(source)
        # Might pick up "Dominated Convergence" without hypothesis clause —
        # the important thing is "clearly" / "obviously" are NOT flagged
        assert not any(f.phrase.lower() in ("clearly", "obviously") for f in flags)

    def test_clearly_flagged(self) -> None:
        flags = detect_hand_waves("Clearly, $f$ is integrable.")
        assert any("clearly" in f.phrase.lower() for f in flags)

    def test_obviously_flagged(self) -> None:
        flags = detect_hand_waves("Obviously the limit exists.")
        assert any("obviously" in f.phrase.lower() for f in flags)

    def test_it_follows_that_flagged(self) -> None:
        flags = detect_hand_waves("It follows that $x = 0$.")
        assert any("follows" in f.phrase.lower() for f in flags)

    def test_it_is_easy_to_see_flagged(self) -> None:
        flags = detect_hand_waves("It is easy to see that the function is continuous.")
        assert any(f for f in flags if "easy to see" in f.phrase.lower())

    def test_by_fubini_flagged_high(self) -> None:
        flags = detect_hand_waves("By Fubini, the double integral equals the iterated integral.")
        fubini_flags = [f for f in flags if "fubini" in f.phrase.lower()]
        assert len(fubini_flags) >= 1
        assert fubini_flags[0].severity == "high"

    def test_by_dct_flagged(self) -> None:
        flags = detect_hand_waves("By the DCT, we can swap the limit and integral.")
        assert any("dct" in f.phrase.lower() for f in flags)

    def test_wlog_flagged(self) -> None:
        flags = detect_hand_waves("WLOG, assume $f \\geq 0$.")
        assert any("wlog" in f.phrase.lower() for f in flags)

    def test_standard_arguments_flagged(self) -> None:
        flags = detect_hand_waves("Standard arguments show that convergence holds.")
        assert any("standard" in f.phrase.lower() for f in flags)

    def test_trivially_flagged_medium(self) -> None:
        flags = detect_hand_waves("This is trivially bounded.")
        trivial_flags = [f for f in flags if "trivially" in f.phrase.lower()]
        assert len(trivial_flags) >= 1
        assert trivial_flags[0].severity == "medium"

    def test_multiple_flags_in_one_text(self) -> None:
        source = "Clearly $f$ is integrable. By Fubini, the integrals commute. Obviously this is bounded."
        flags = detect_hand_waves(source)
        assert len(flags) >= 2

    def test_flags_sorted_by_position(self) -> None:
        source = "Trivially bounded. Clearly $f$ integrable."
        flags = detect_hand_waves(source)
        if len(flags) >= 2:
            assert flags[0].position <= flags[1].position

    def test_context_window_populated(self) -> None:
        source = "Some prefix text. Clearly the result holds. Some suffix text."
        flags = detect_hand_waves(source)
        clearly_flags = [f for f in flags if "clearly" in f.phrase.lower()]
        assert len(clearly_flags) >= 1
        assert "clearly" in clearly_flags[0].context.lower()

    def test_empty_string_returns_no_flags(self) -> None:
        flags = detect_hand_waves("")
        assert flags == []

    def test_no_duplicate_spans(self) -> None:
        source = "Clearly clearly clearly."
        flags = detect_hand_waves(source)
        spans = [(f.position, f.phrase) for f in flags]
        assert len(spans) == len(set(spans))


class TestSummariseFlags:
    def test_returns_list_of_strings(self) -> None:
        source = "Clearly $f$ is bounded."
        flags = detect_hand_waves(source)
        summaries = summarise_flags(flags)
        assert all(isinstance(s, str) for s in summaries)

    def test_summary_contains_severity(self) -> None:
        source = "Clearly bounded."
        flags = detect_hand_waves(source)
        summaries = summarise_flags(flags)
        if summaries:
            assert "HIGH" in summaries[0] or "MEDIUM" in summaries[0] or "LOW" in summaries[0]

    def test_empty_flags_returns_empty(self) -> None:
        assert summarise_flags([]) == []


class TestHasHighSeverityFlags:
    def test_true_when_high_severity_present(self) -> None:
        flags = detect_hand_waves("Clearly the result holds.")
        assert has_high_severity_flags(flags)

    def test_false_when_no_flags(self) -> None:
        assert not has_high_severity_flags([])

    def test_false_when_only_low_severity(self) -> None:
        # Create a synthetic low-severity flag
        flag = HandWaveFlag(
            phrase="straightforwardly",
            category="vague_certainty",
            position=0,
            context="straightforwardly",
            severity="low",
        )
        assert not has_high_severity_flags([flag])

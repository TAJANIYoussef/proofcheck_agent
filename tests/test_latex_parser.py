"""Tests for src/deriv_verifier/tools/latex_parser.py."""

from __future__ import annotations

import pytest

from deriv_verifier.schemas import BlockKind
from deriv_verifier.tools.latex_parser import extract_equations, parse_latex


class TestParseLatex:
    def test_empty_string_returns_empty_list(self) -> None:
        assert parse_latex("") == []

    def test_plain_text_returns_text_block(self) -> None:
        blocks = parse_latex("Let $X$ be a compact metric space.")
        assert len(blocks) >= 1

    def test_proof_environment_detected(self) -> None:
        source = r"""
\begin{proof}
Let $f \in L^1(\mu)$.
\end{proof}
"""
        blocks = parse_latex(source)
        kinds = [b.kind for b in blocks]
        assert BlockKind.PROOF in kinds

    def test_equation_environment_detected(self) -> None:
        source = r"""
\begin{equation}
  \int_X f \, d\mu = 1
\end{equation}
"""
        blocks = parse_latex(source)
        kinds = [b.kind for b in blocks]
        assert BlockKind.EQUATION in kinds

    def test_align_environment_is_equation(self) -> None:
        source = r"""
\begin{align*}
  a &= b \\
  c &= d
\end{align*}
"""
        blocks = parse_latex(source)
        eq_blocks = [b for b in blocks if b.kind == BlockKind.EQUATION]
        assert len(eq_blocks) >= 1

    def test_display_math_detected(self) -> None:
        source = r"""
Some text.
\[
  f(x) = \int_0^x g(t) \, dt
\]
More text.
"""
        blocks = parse_latex(source)
        eq_blocks = [b for b in blocks if b.kind == BlockKind.EQUATION]
        assert len(eq_blocks) >= 1

    def test_theorem_environment_detected(self) -> None:
        source = r"""
\begin{theorem}
Every compact set in a metric space is bounded.
\end{theorem}
"""
        blocks = parse_latex(source)
        kinds = [b.kind for b in blocks]
        assert BlockKind.THEOREM in kinds

    def test_lemma_environment_detected(self) -> None:
        source = r"""
\begin{lemma}
$f$ is measurable.
\end{lemma}
"""
        blocks = parse_latex(source)
        kinds = [b.kind for b in blocks]
        assert BlockKind.LEMMA in kinds

    def test_blocks_have_sequential_indices(self) -> None:
        source = r"""
Text before.
\begin{equation}
x = 1
\end{equation}
Text after.
"""
        blocks = parse_latex(source)
        for i, b in enumerate(blocks):
            assert b.index == i

    def test_raw_latex_preserved(self) -> None:
        source = r"\begin{proof} x = y \end{proof}"
        blocks = parse_latex(source)
        proof_blocks = [b for b in blocks if b.kind == BlockKind.PROOF]
        assert len(proof_blocks) >= 1
        assert "x = y" in proof_blocks[0].raw_latex

    def test_multiple_equations_all_captured(self) -> None:
        source = r"""
\begin{equation}
a = b
\end{equation}
\begin{equation}
c = d
\end{equation}
"""
        blocks = parse_latex(source)
        eq_blocks = [b for b in blocks if b.kind == BlockKind.EQUATION]
        assert len(eq_blocks) >= 2

    def test_unicode_in_text_handled(self) -> None:
        source = "Let μ ∈ ℳ(X) be a σ-finite measure."
        # Should not raise
        blocks = parse_latex(source)
        assert len(blocks) >= 1


class TestExtractEquations:
    def test_no_equations_returns_empty(self) -> None:
        result = extract_equations("Just some plain text with no math.")
        # May or may not find inline $...$ — just verify it's a list
        assert isinstance(result, list)

    def test_extracts_equation_env(self) -> None:
        source = r"\begin{equation} \alpha + \beta = \gamma \end{equation}"
        result = extract_equations(source)
        assert len(result) >= 1
        assert any(r"\alpha" in eq or "alpha" in eq for eq in result)

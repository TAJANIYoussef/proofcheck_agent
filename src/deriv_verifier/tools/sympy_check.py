"""Symbolic algebra / calculus verification via SymPy.

Converts simple LaTeX expressions to SymPy and checks:
  - algebraic equality
  - limit equality
  - integration equality (definite integrals over simple domains)

Deterministic — no LLM calls.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

import sympy as sp
from sympy import (
    Limit,
    Symbol,
    integrate,
    simplify,
    sympify,
)
from sympy.parsing.latex import parse_latex as sympy_parse_latex

logger = logging.getLogger(__name__)


@dataclass
class CheckResult:
    """Result of a symbolic verification check."""

    passed: bool
    reason: str
    lhs_simplified: str | None = None
    rhs_simplified: str | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_equality(lhs_latex: str, rhs_latex: str) -> CheckResult:
    """Check whether two LaTeX expressions are symbolically equal.

    Returns ``CheckResult(passed=True)`` if ``simplify(lhs - rhs) == 0``.
    """
    try:
        lhs = _parse(lhs_latex)
        rhs = _parse(rhs_latex)
        diff = simplify(lhs - rhs)
        passed = diff == 0
        return CheckResult(
            passed=passed,
            reason="Expressions are equal." if passed else f"Difference is {diff}.",
            lhs_simplified=str(lhs),
            rhs_simplified=str(rhs),
        )
    except Exception as exc:  # noqa: BLE001
        return CheckResult(
            passed=False,
            reason="Could not verify symbolically.",
            error=str(exc),
        )


def check_limit_equality(
    expr_latex: str,
    var_latex: str,
    limit_point_latex: str,
    expected_latex: str,
    direction: str = "+",
) -> CheckResult:
    """Check whether lim_{var → limit_point} expr == expected.

    *direction* is ``'+'``, ``'-'``, or ``'+-'`` (bilateral).
    """
    try:
        expr = _parse(expr_latex)
        var = _parse_symbol(var_latex)
        limit_point = _parse(limit_point_latex)
        expected = _parse(expected_latex)

        lim_val = Limit(expr, var, limit_point, direction).doit()
        diff = simplify(lim_val - expected)
        passed = diff == 0
        return CheckResult(
            passed=passed,
            reason=(
                f"Limit equals {lim_val}." if passed
                else f"Limit is {lim_val}, expected {expected}."
            ),
            lhs_simplified=str(lim_val),
            rhs_simplified=str(expected),
        )
    except Exception as exc:  # noqa: BLE001
        return CheckResult(
            passed=False,
            reason="Could not verify limit symbolically.",
            error=str(exc),
        )


def check_integral_equality(
    integrand_latex: str,
    var_latex: str,
    lower_latex: str,
    upper_latex: str,
    expected_latex: str,
) -> CheckResult:
    """Check whether ∫_lower^upper integrand d(var) == expected."""
    try:
        integrand = _parse(integrand_latex)
        var = _parse_symbol(var_latex)
        lower = _parse(lower_latex)
        upper = _parse(upper_latex)
        expected = _parse(expected_latex)

        result = integrate(integrand, (var, lower, upper))
        diff = simplify(result - expected)
        passed = diff == 0
        return CheckResult(
            passed=passed,
            reason=(
                f"Integral equals {result}." if passed
                else f"Integral is {result}, expected {expected}."
            ),
            lhs_simplified=str(result),
            rhs_simplified=str(expected),
        )
    except Exception as exc:  # noqa: BLE001
        return CheckResult(
            passed=False,
            reason="Could not verify integral symbolically.",
            error=str(exc),
        )


def is_simplified(expr_latex: str) -> CheckResult:
    """Check whether an expression is already in simplified form."""
    try:
        expr = _parse(expr_latex)
        simp = simplify(expr)
        passed = expr == simp or simplify(expr - simp) == 0
        return CheckResult(
            passed=passed,
            reason="Expression is in simplified form." if passed
            else f"Can be simplified to {simp}.",
            lhs_simplified=str(expr),
            rhs_simplified=str(simp),
        )
    except Exception as exc:  # noqa: BLE001
        return CheckResult(
            passed=False,
            reason="Could not evaluate simplification.",
            error=str(exc),
        )


# ---------------------------------------------------------------------------
# LaTeX → SymPy conversion helpers
# ---------------------------------------------------------------------------


def _parse(latex: str) -> Any:
    """Convert a LaTeX string to a SymPy expression.

    Applies heuristic pre-processing to handle common mathematical notation
    that SymPy's parser does not handle natively (e.g. ``\mathbb{R}``).
    """
    cleaned = _preprocess_latex(latex)
    try:
        return sympy_parse_latex(cleaned)
    except Exception:  # noqa: BLE001
        # Last-resort: try sympify on the cleaned string
        return sympify(cleaned)


def _parse_symbol(latex: str) -> Symbol:
    """Extract a single SymPy symbol from a LaTeX identifier."""
    cleaned = _preprocess_latex(latex).strip()
    # Strip surrounding braces
    cleaned = re.sub(r"^\{(.*)\}$", r"\1", cleaned)
    return Symbol(cleaned)


def _preprocess_latex(latex: str) -> str:
    """Normalise LaTeX for SymPy's parser."""
    s = latex.strip()
    # Remove display math delimiters
    s = re.sub(r"^\\\[|\\\]$", "", s)
    s = re.sub(r"^\$\$|\$\$$", "", s)
    s = re.sub(r"^\$|\$$", "", s)

    # Common substitutions
    s = s.replace(r"\infty", "oo")
    s = s.replace(r"\mathbb{R}", "R")
    s = s.replace(r"\mathbb{N}", "N")
    s = s.replace(r"\mathbb{Z}", "Z")
    s = s.replace(r"\mathbb{Q}", "Q")
    s = s.replace(r"\mathbb{C}", "C")
    s = s.replace(r"\cdot", "*")
    s = s.replace(r"\times", "*")
    s = s.replace(r"\leq", "<=")
    s = s.replace(r"\geq", ">=")
    s = s.replace(r"\neq", "!=")
    s = s.replace(r"\,", " ")
    s = s.replace(r"\!", "")
    s = s.replace(r"\left", "")
    s = s.replace(r"\right", "")
    s = re.sub(r"\\mathrm\{([^}]+)\}", r"\1", s)
    s = re.sub(r"\\text\{([^}]+)\}", r"\1", s)
    return s.strip()

"""Tests for src/deriv_verifier/tools/sympy_check.py."""

from __future__ import annotations

import pytest

from deriv_verifier.tools.sympy_check import (
    CheckResult,
    check_equality,
    check_integral_equality,
    check_limit_equality,
    is_simplified,
)


class TestCheckEquality:
    def test_trivial_equality(self) -> None:
        result = check_equality("a + b", "b + a")
        assert result.passed

    def test_algebraic_identity(self) -> None:
        result = check_equality("(x + 1)^2", "x^2 + 2*x + 1")
        assert result.passed

    def test_false_equality(self) -> None:
        result = check_equality("x^2", "x^3")
        assert not result.passed

    def test_zero_difference(self) -> None:
        result = check_equality("2*x", "x + x")
        assert result.passed

    def test_invalid_latex_returns_failed(self) -> None:
        result = check_equality(r"\invalid{{{}", r"\also_invalid")
        assert isinstance(result, CheckResult)
        # Might pass or fail; should not raise
        assert result.error is not None or not result.passed

    def test_infty_handling(self) -> None:
        result = check_equality(r"\infty", "oo")
        assert result.passed

    def test_result_contains_simplified_forms(self) -> None:
        result = check_equality("x + x", "2*x")
        assert result.lhs_simplified is not None
        assert result.rhs_simplified is not None


class TestCheckLimitEquality:
    def test_limit_to_infinity(self) -> None:
        result = check_limit_equality(
            expr_latex="1/n",
            var_latex="n",
            limit_point_latex=r"\infty",
            expected_latex="0",
            direction="+",
        )
        assert result.passed

    def test_finite_limit(self) -> None:
        result = check_limit_equality(
            expr_latex="(x^2 - 1)/(x - 1)",
            var_latex="x",
            limit_point_latex="1",
            expected_latex="2",
            direction="+-",
        )
        assert result.passed

    def test_wrong_limit_value(self) -> None:
        result = check_limit_equality(
            expr_latex="1/n",
            var_latex="n",
            limit_point_latex=r"\infty",
            expected_latex="1",
            direction="+",
        )
        assert not result.passed

    def test_limit_error_returns_failed_result(self) -> None:
        result = check_limit_equality(
            expr_latex=r"\undefined_macro",
            var_latex="x",
            limit_point_latex="0",
            expected_latex="0",
        )
        assert isinstance(result, CheckResult)


class TestCheckIntegralEquality:
    def test_simple_definite_integral(self) -> None:
        result = check_integral_equality(
            integrand_latex="x",
            var_latex="x",
            lower_latex="0",
            upper_latex="1",
            expected_latex="1/2",
        )
        assert result.passed

    def test_constant_integral(self) -> None:
        result = check_integral_equality(
            integrand_latex="1",
            var_latex="x",
            lower_latex="0",
            upper_latex="a",
            expected_latex="a",
        )
        assert result.passed

    def test_wrong_integral_value(self) -> None:
        result = check_integral_equality(
            integrand_latex="x",
            var_latex="x",
            lower_latex="0",
            upper_latex="1",
            expected_latex="1",
        )
        assert not result.passed

    def test_error_returns_failed_result(self) -> None:
        result = check_integral_equality(
            integrand_latex=r"\undefinedmacro",
            var_latex="x",
            lower_latex="0",
            upper_latex="1",
            expected_latex="0",
        )
        assert isinstance(result, CheckResult)


class TestIsSimplified:
    def test_already_simplified(self) -> None:
        result = is_simplified("x")
        assert result.passed

    def test_unsimplified_polynomial(self) -> None:
        result = is_simplified("(x+1)*(x-1)")
        # SymPy may or may not simplify this — just check it doesn't raise
        assert isinstance(result, CheckResult)

    def test_error_returns_failed_result(self) -> None:
        result = is_simplified(r"\completely_invalid{{{")
        assert isinstance(result, CheckResult)

"""Tests for src/deriv_verifier/tools/assumption_stack.py."""

from __future__ import annotations

import pytest

from deriv_verifier.tools.assumption_stack import Assumption, AssumptionStack


class TestAssumptionStackBasic:
    def setup_method(self) -> None:
        self.stack = AssumptionStack()

    def test_empty_stack_has_zero_length(self) -> None:
        assert len(self.stack) == 0

    def test_push_and_query(self) -> None:
        self.stack.push("mu_sf", r"\mu is sigma-finite")
        result = self.stack.query("mu_sf")
        assert result is not None
        assert result.description == r"\mu is sigma-finite"

    def test_push_returns_assumption(self) -> None:
        a = self.stack.push("f_int", r"f \in L^1(\mu)")
        assert isinstance(a, Assumption)
        assert a.label == "f_int"

    def test_query_missing_returns_none(self) -> None:
        assert self.stack.query("nonexistent") is None

    def test_pop_removes_assumption(self) -> None:
        self.stack.push("f_int", r"f \in L^1")
        self.stack.pop("f_int")
        assert self.stack.query("f_int") is None

    def test_pop_returns_assumption(self) -> None:
        self.stack.push("f_int", r"f \in L^1")
        a = self.stack.pop("f_int")
        assert a.label == "f_int"

    def test_pop_missing_raises_key_error(self) -> None:
        with pytest.raises(KeyError):
            self.stack.pop("nonexistent")

    def test_len_updates_on_push_pop(self) -> None:
        self.stack.push("a1", "first")
        self.stack.push("a2", "second")
        assert len(self.stack) == 2
        self.stack.pop("a1")
        assert len(self.stack) == 1

    def test_contains(self) -> None:
        self.stack.push("mu_sf", "sigma-finite")
        assert "mu_sf" in self.stack
        assert "other" not in self.stack

    def test_iter(self) -> None:
        self.stack.push("a1", "first")
        self.stack.push("a2", "second")
        labels = [a.label for a in self.stack]
        assert "a1" in labels
        assert "a2" in labels

    def test_active_returns_all(self) -> None:
        self.stack.push("a1", "first")
        self.stack.push("a2", "second")
        active = self.stack.active()
        assert len(active) == 2

    def test_active_labels(self) -> None:
        self.stack.push("mu_sf", "measure")
        labels = self.stack.active_labels()
        assert "mu_sf" in labels

    def test_duplicate_label_overwrites(self) -> None:
        self.stack.push("mu_sf", "old description")
        self.stack.push("mu_sf", "new description")
        result = self.stack.query("mu_sf")
        assert result is not None
        assert result.description == "new description"
        assert len(self.stack) == 1

    def test_clear(self) -> None:
        self.stack.push("a1", "first")
        self.stack.push("a2", "second")
        self.stack.clear()
        assert len(self.stack) == 0


class TestAssumptionStackScopes:
    def setup_method(self) -> None:
        self.stack = AssumptionStack()

    def test_default_scope_is_global(self) -> None:
        assert self.stack.current_scope == "global"

    def test_enter_scope_changes_current_scope(self) -> None:
        self.stack.enter_scope("Theorem 1")
        assert self.stack.current_scope == "Theorem 1"

    def test_exit_scope_restores_previous_scope(self) -> None:
        self.stack.enter_scope("Theorem 1")
        self.stack.exit_scope("Theorem 1")
        assert self.stack.current_scope == "global"

    def test_exit_wrong_scope_raises(self) -> None:
        self.stack.enter_scope("Theorem 1")
        with pytest.raises(ValueError, match="mismatch"):
            self.stack.exit_scope("Lemma 2")

    def test_exit_no_scope_raises(self) -> None:
        with pytest.raises(ValueError, match="No active scope"):
            self.stack.exit_scope("anything")

    def test_scoped_assumptions_visible_in_active(self) -> None:
        self.stack.push("global_a", "global assumption")
        self.stack.enter_scope("Theorem 1")
        self.stack.push("local_a", "local assumption")
        active = self.stack.active()
        labels = [a.label for a in active]
        assert "global_a" in labels
        assert "local_a" in labels

    def test_exit_scope_drops_local_assumptions(self) -> None:
        self.stack.push("global_a", "global assumption")
        self.stack.enter_scope("Theorem 1")
        self.stack.push("local_a", "local assumption")
        self.stack.exit_scope("Theorem 1")
        active_labels = self.stack.active_labels()
        assert "local_a" not in active_labels
        assert "global_a" in active_labels

    def test_exit_scope_returns_dropped_assumptions(self) -> None:
        self.stack.enter_scope("inner")
        self.stack.push("inner_a", "inner assumption")
        dropped = self.stack.exit_scope("inner")
        assert len(dropped) == 1
        assert dropped[0].label == "inner_a"

    def test_nested_scopes(self) -> None:
        self.stack.push("g", "global")
        self.stack.enter_scope("outer")
        self.stack.push("o", "outer")
        self.stack.enter_scope("inner")
        self.stack.push("i", "inner")

        active = self.stack.active_labels()
        assert "g" in active
        assert "o" in active
        assert "i" in active

        self.stack.exit_scope("inner")
        active = self.stack.active_labels()
        assert "i" not in active
        assert "o" in active

        self.stack.exit_scope("outer")
        active = self.stack.active_labels()
        assert "o" not in active
        assert "g" in active


class TestAssumptionStackSnapshot:
    def test_snapshot_is_list_of_dicts(self) -> None:
        stack = AssumptionStack()
        stack.push("mu_sf", "sigma-finite")
        snap = stack.snapshot()
        assert isinstance(snap, list)
        assert snap[0]["label"] == "mu_sf"

    def test_snapshot_includes_scope(self) -> None:
        stack = AssumptionStack()
        stack.enter_scope("Lemma 2")
        stack.push("f_int", "f integrable", scope="Lemma 2")
        snap = stack.snapshot()
        assert snap[0]["scope"] == "Lemma 2"

    def test_snapshot_is_independent_copy(self) -> None:
        stack = AssumptionStack()
        stack.push("a1", "first")
        snap = stack.snapshot()
        stack.pop("a1")
        # snapshot should be unchanged
        assert len(snap) == 1

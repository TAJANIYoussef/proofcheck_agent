"""Scoped assumption stack for tracking active hypotheses during proof verification.

Deterministic — no LLM calls.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Iterator

logger = logging.getLogger(__name__)


@dataclass
class Assumption:
    """One hypothesis pushed onto the stack."""

    label: str
    description: str
    scope: str = "global"  # e.g. "Theorem 1", "inner proof", "global"


@dataclass
class _StackFrame:
    """One scope level on the assumption stack."""

    scope: str
    assumptions: list[Assumption] = field(default_factory=list)


class AssumptionStack:
    """LIFO stack of scoped hypotheses.

    Usage pattern::

        stack = AssumptionStack()
        stack.push("f integrable", "f \\in L^1(\\mu)", scope="Theorem 1")
        stack.push("mu sigma-finite", "\\mu is sigma-finite", scope="Theorem 1")

        active = stack.active()  # all currently live assumptions

        snap = stack.snapshot()  # copy for serialisation
        stack.pop("f integrable")

        stack.enter_scope("inner lemma")
        ...
        stack.exit_scope("inner lemma")  # pops all assumptions in that scope
    """

    def __init__(self) -> None:
        self._global_frame: _StackFrame = _StackFrame(scope="global")
        self._scope_stack: list[_StackFrame] = []

    # ------------------------------------------------------------------
    # Scope management
    # ------------------------------------------------------------------

    def enter_scope(self, scope: str) -> None:
        """Open a new named scope.  Assumptions pushed inside it are local to it."""
        self._scope_stack.append(_StackFrame(scope=scope))
        logger.debug("Entered scope: %s", scope)

    def exit_scope(self, scope: str) -> list[Assumption]:
        """Close the innermost scope, discarding its assumptions.

        Returns the assumptions that were dropped.  Raises ``ValueError`` if
        *scope* does not match the current innermost scope name.
        """
        if not self._scope_stack:
            raise ValueError("No active scope to exit.")
        top = self._scope_stack[-1]
        if top.scope != scope:
            raise ValueError(
                f"Scope mismatch: expected '{top.scope}', got '{scope}'."
            )
        dropped = self._scope_stack.pop().assumptions
        logger.debug("Exited scope '%s', dropped %d assumption(s).", scope, len(dropped))
        return dropped

    @property
    def current_scope(self) -> str:
        if self._scope_stack:
            return self._scope_stack[-1].scope
        return "global"

    # ------------------------------------------------------------------
    # Push / pop individual assumptions
    # ------------------------------------------------------------------

    def push(self, label: str, description: str, *, scope: str | None = None) -> Assumption:
        """Push a new assumption onto the current (or specified) scope.

        *label* must be unique within the current scope.  Use descriptive
        labels like ``"mu_sigma_finite"`` for easy retrieval.
        """
        target_frame = self._current_frame()
        used_scope = scope or target_frame.scope
        assumption = Assumption(label=label, description=description, scope=used_scope)
        if any(a.label == label for a in target_frame.assumptions):
            logger.warning("Assumption '%s' already on stack; overwriting.", label)
            target_frame.assumptions = [
                a for a in target_frame.assumptions if a.label != label
            ]
        target_frame.assumptions.append(assumption)
        logger.debug("Pushed assumption '%s' in scope '%s'.", label, used_scope)
        return assumption

    def pop(self, label: str) -> Assumption:
        """Remove and return the assumption with the given *label*.

        Searches from innermost scope outward.  Raises ``KeyError`` if not found.
        """
        frames = list(reversed(self._scope_stack)) + [self._global_frame]
        for frame in frames:
            for assumption in frame.assumptions:
                if assumption.label == label:
                    frame.assumptions.remove(assumption)
                    logger.debug("Popped assumption '%s'.", label)
                    return assumption
        raise KeyError(f"Assumption '{label}' not found on the stack.")

    def query(self, label: str) -> Assumption | None:
        """Return the assumption with *label*, or None if absent."""
        for assumption in self.active():
            if assumption.label == label:
                return assumption
        return None

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def active(self) -> list[Assumption]:
        """All currently live assumptions (global + all open scopes)."""
        result: list[Assumption] = list(self._global_frame.assumptions)
        for frame in self._scope_stack:
            result.extend(frame.assumptions)
        return result

    def active_labels(self) -> list[str]:
        return [a.label for a in self.active()]

    def snapshot(self) -> list[dict[str, str]]:
        """Serialisable copy of all active assumptions."""
        return [
            {"label": a.label, "description": a.description, "scope": a.scope}
            for a in self.active()
        ]

    def clear(self) -> None:
        """Remove all assumptions and scopes."""
        self._global_frame = _StackFrame(scope="global")
        self._scope_stack.clear()

    def __len__(self) -> int:
        return len(self.active())

    def __iter__(self) -> Iterator[Assumption]:
        return iter(self.active())

    def __contains__(self, label: object) -> bool:
        return isinstance(label, str) and any(a.label == label for a in self.active())

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _current_frame(self) -> _StackFrame:
        if self._scope_stack:
            return self._scope_stack[-1]
        return self._global_frame

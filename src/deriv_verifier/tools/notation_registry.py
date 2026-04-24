"""Notation registry: YAML-backed, per-project symbol dictionary.

Deterministic — no LLM calls.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterator

import yaml

from deriv_verifier.schemas import NotationEntry, NotationType

logger = logging.getLogger(__name__)


class NotationRegistry:
    """In-memory registry that can be persisted to / loaded from YAML."""

    def __init__(self) -> None:
        self._entries: dict[str, NotationEntry] = {}

    # ------------------------------------------------------------------
    # I/O
    # ------------------------------------------------------------------

    @classmethod
    def from_yaml(cls, path: str | Path) -> "NotationRegistry":
        """Load registry from a YAML file."""
        path = Path(path)
        registry = cls()
        if not path.exists():
            logger.debug("Notation file %s not found; starting empty registry.", path)
            return registry
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        for symbol, fields in data.items():
            try:
                entry = NotationEntry.model_validate({"symbol": symbol, **fields})
                registry._entries[symbol] = entry
            except Exception as exc:  # noqa: BLE001
                logger.warning("Skipping invalid notation entry '%s': %s", symbol, exc)
        logger.info("Loaded %d notation entries from %s.", len(registry._entries), path)
        return registry

    def to_yaml(self, path: str | Path) -> None:
        """Persist registry to a YAML file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data: dict[str, object] = {}
        for symbol, entry in sorted(self._entries.items()):
            entry_dict = entry.model_dump(exclude={"symbol"})
            # Convert enums to string values for clean YAML
            entry_dict["type"] = entry.type.value
            data[symbol] = entry_dict
        with path.open("w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=True)
        logger.info("Saved %d notation entries to %s.", len(data), path)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def register(
        self,
        symbol: str,
        type: NotationType,  # noqa: A002
        *,
        space: str | None = None,
        assumptions: list[str] | None = None,
        first_defined_at: str | None = None,
        description: str | None = None,
        overwrite: bool = False,
    ) -> NotationEntry:
        """Add or update a symbol in the registry."""
        if symbol in self._entries and not overwrite:
            raise ValueError(
                f"Symbol '{symbol}' already registered. Use overwrite=True to update."
            )
        entry = NotationEntry(
            symbol=symbol,
            type=type,
            space=space,
            assumptions=assumptions or [],
            first_defined_at=first_defined_at,
            description=description,
        )
        self._entries[symbol] = entry
        return entry

    def query(self, symbol: str) -> NotationEntry | None:
        """Return the entry for *symbol*, or None if not registered."""
        return self._entries.get(symbol)

    def remove(self, symbol: str) -> bool:
        """Remove *symbol* from the registry. Returns True if it existed."""
        existed = symbol in self._entries
        self._entries.pop(symbol, None)
        return existed

    def all_entries(self) -> list[NotationEntry]:
        return list(self._entries.values())

    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self) -> Iterator[NotationEntry]:
        return iter(self._entries.values())

    def __contains__(self, symbol: object) -> bool:
        return symbol in self._entries

    # ------------------------------------------------------------------
    # Conflict detection
    # ------------------------------------------------------------------

    def conflict_check(self, source: str) -> list[str]:
        """Scan *source* LaTeX for symbols that appear but are unregistered.

        Returns a list of LaTeX control sequences found in *source* that are
        not in the registry (and look like they might be mathematical symbols).
        """
        import re

        # Match \command or \command{...} patterns (skip pure formatting macros)
        _FORMATTING = {
            r"\text", r"\textbf", r"\textit", r"\emph", r"\label", r"\ref",
            r"\cite", r"\footnote", r"\begin", r"\end", r"\left", r"\right",
            r"\quad", r"\qquad", r"\,", r"\!", r"\;", r"\:", r"\.", r"\\",
        }
        found: set[str] = set(re.findall(r"\\[a-zA-Z]+", source))
        unregistered = sorted(
            sym for sym in found if sym not in self._entries and sym not in _FORMATTING
        )
        return unregistered

    def redefition_check(self, symbol: str, new_type: NotationType) -> bool:
        """Return True if *symbol* is already registered with a different type."""
        existing = self._entries.get(symbol)
        if existing is None:
            return False
        return existing.type != new_type

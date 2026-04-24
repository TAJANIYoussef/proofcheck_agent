"""Tests for src/deriv_verifier/tools/notation_registry.py."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml

from deriv_verifier.schemas import NotationType
from deriv_verifier.tools.notation_registry import NotationRegistry


class TestNotationRegistryCRUD:
    def setup_method(self) -> None:
        self.registry = NotationRegistry()

    def test_register_and_query(self) -> None:
        self.registry.register(r"\mu", NotationType.MEASURE)
        entry = self.registry.query(r"\mu")
        assert entry is not None
        assert entry.symbol == r"\mu"
        assert entry.type == NotationType.MEASURE

    def test_query_missing_returns_none(self) -> None:
        assert self.registry.query(r"\unknown") is None

    def test_register_with_all_fields(self) -> None:
        entry = self.registry.register(
            r"\pi",
            NotationType.MEASURE,
            space=r"\mathcal{P}(X \times Y)",
            assumptions=["coupling", "probability"],
            first_defined_at="Section 2",
            description="Coupling measure",
        )
        assert entry.space == r"\mathcal{P}(X \times Y)"
        assert "coupling" in entry.assumptions
        assert entry.first_defined_at == "Section 2"

    def test_register_duplicate_raises(self) -> None:
        self.registry.register(r"\mu", NotationType.MEASURE)
        with pytest.raises(ValueError, match="already registered"):
            self.registry.register(r"\mu", NotationType.FUNCTION)

    def test_register_with_overwrite(self) -> None:
        self.registry.register(r"\mu", NotationType.MEASURE)
        self.registry.register(r"\mu", NotationType.FUNCTION, overwrite=True)
        entry = self.registry.query(r"\mu")
        assert entry is not None
        assert entry.type == NotationType.FUNCTION

    def test_remove_existing_returns_true(self) -> None:
        self.registry.register(r"\mu", NotationType.MEASURE)
        assert self.registry.remove(r"\mu") is True
        assert self.registry.query(r"\mu") is None

    def test_remove_missing_returns_false(self) -> None:
        assert self.registry.remove(r"\unknown") is False

    def test_len(self) -> None:
        assert len(self.registry) == 0
        self.registry.register(r"\mu", NotationType.MEASURE)
        assert len(self.registry) == 1
        self.registry.register(r"\nu", NotationType.MEASURE)
        assert len(self.registry) == 2

    def test_contains(self) -> None:
        self.registry.register(r"\mu", NotationType.MEASURE)
        assert r"\mu" in self.registry
        assert r"\nu" not in self.registry

    def test_all_entries(self) -> None:
        self.registry.register(r"\mu", NotationType.MEASURE)
        self.registry.register(r"\f", NotationType.FUNCTION)
        entries = self.registry.all_entries()
        assert len(entries) == 2

    def test_iter(self) -> None:
        self.registry.register(r"\mu", NotationType.MEASURE)
        entries = list(self.registry)
        assert len(entries) == 1


class TestNotationRegistryYAML:
    def test_round_trip_yaml(self) -> None:
        registry = NotationRegistry()
        registry.register(
            r"\mu",
            NotationType.MEASURE,
            space=r"\mathcal{M}(X)",
            assumptions=["sigma-finite"],
        )
        registry.register(r"\f", NotationType.FUNCTION, description="density")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "notation.yaml"
            registry.to_yaml(path)

            loaded = NotationRegistry.from_yaml(path)
            assert len(loaded) == 2
            mu = loaded.query(r"\mu")
            assert mu is not None
            assert mu.type == NotationType.MEASURE
            assert "sigma-finite" in mu.assumptions

    def test_from_yaml_missing_file_returns_empty(self) -> None:
        registry = NotationRegistry.from_yaml("/nonexistent/path/notation.yaml")
        assert len(registry) == 0

    def test_from_yaml_with_fixture(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "notation_reference.yaml"
        if fixture.exists():
            registry = NotationRegistry.from_yaml(fixture)
            assert len(registry) >= 1

    def test_to_yaml_creates_parent_dirs(self) -> None:
        registry = NotationRegistry()
        registry.register(r"\mu", NotationType.MEASURE)
        with tempfile.TemporaryDirectory() as tmpdir:
            nested = Path(tmpdir) / "subdir" / "notation.yaml"
            registry.to_yaml(nested)
            assert nested.exists()


class TestConflictDetection:
    def setup_method(self) -> None:
        self.registry = NotationRegistry()
        self.registry.register(r"\mu", NotationType.MEASURE)
        self.registry.register(r"\alpha", NotationType.SCALAR)

    def test_registered_symbols_not_flagged(self) -> None:
        source = r"Let $\mu$ be a measure and $\alpha > 0$."
        unregistered = self.registry.conflict_check(source)
        assert r"\mu" not in unregistered
        assert r"\alpha" not in unregistered

    def test_unregistered_symbol_flagged(self) -> None:
        source = r"Let $\nu$ be another measure."
        unregistered = self.registry.conflict_check(source)
        assert r"\nu" in unregistered

    def test_formatting_macros_excluded(self) -> None:
        source = r"\text{Let } \begin{equation} x \end{equation}"
        unregistered = self.registry.conflict_check(source)
        assert r"\text" not in unregistered
        assert r"\begin" not in unregistered

    def test_redefinition_check_same_type(self) -> None:
        assert self.registry.redefition_check(r"\mu", NotationType.MEASURE) is False

    def test_redefinition_check_different_type(self) -> None:
        assert self.registry.redefition_check(r"\mu", NotationType.FUNCTION) is True

    def test_redefinition_check_missing_symbol(self) -> None:
        assert self.registry.redefition_check(r"\unknown", NotationType.SCALAR) is False

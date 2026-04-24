# Changelog

All notable changes to Derivation Verifier are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [unreleased] — 2026-04-22

### Fixed
- `src/deriv_verifier/llm.py`: `result_type=` kwarg to `Agent()` renamed to `output_type=`
  in PydanticAI 1.x; return type annotation updated from `Agent[None, T]` to `Agent[T]`.
- `src/deriv_verifier/agents/decomposer.py`: `result.data` → `result.output` (PydanticAI 1.x
  renamed `RunResult.data` to `RunResult.output`).
- `src/deriv_verifier/agents/critic.py`: same `result.data` → `result.output` fix.
- `src/deriv_verifier/agents/rewriter.py`: same `result.data` → `result.output` fix.
- `src/deriv_verifier/agents/verifier.py`: same `result.data` → `result.output` fix (×2).
- `src/deriv_verifier/llm.py`: ported to PydanticAI ≥1.x API — replaced `OpenAIModel`
  (which accepted `base_url`/`api_key` directly) with `OpenAIChatModel` (from
  `pydantic_ai.models.openai`) backed by an `OpenAIProvider` (from
  `pydantic_ai.providers.openai`) that carries the transport config. Updated
  `make_openai_model()` return type and `make_agent()` `model` parameter type accordingly.

### Added
- `CLAUDE.md`: project memory file with stack, conventions, decisions, limitations.
- `CHANGELOG.md`: this file; tracks all source-level changes.
- `README.md`: user-facing setup and usage documentation.
- `requirements.txt`: pinned dependencies for all phases.
- `pyproject.toml`: package configuration (name, entry point, tool settings).
- `.gitignore`: excludes `.env`, `__pycache__`, `.mypy_cache`, session files, etc.
- `.env.example`: template for local environment variables.
- `src/deriv_verifier/__init__.py`: package root with version constant.
- `src/deriv_verifier/cli.py`: skeleton `typer` entrypoint (stub, no logic yet).
- `src/deriv_verifier/config.py`: pydantic-settings `Settings` class.
- `src/deriv_verifier/schemas.py`: `StepRecord`, `NotationEntry`, `AtomicStep`, `DerivationBlock`, `VerificationReport` pydantic models.
- `src/deriv_verifier/llm.py`: PydanticAI `Agent` factory bound to Ollama OpenAI-compatible endpoint.
- `src/deriv_verifier/pipeline.py`: orchestrator that ties all pipeline stages together.
- `src/deriv_verifier/agents/__init__.py`: agents sub-package marker.
- `src/deriv_verifier/agents/parser.py`: LaTeX cleaning + handoff to `latex_parser` tool.
- `src/deriv_verifier/agents/decomposer.py`: LLM-backed block → `AtomicStep` list.
- `src/deriv_verifier/agents/verifier.py`: CoVe verifier, returns `StepRecord` per step.
- `src/deriv_verifier/agents/critic.py`: second-pass critic for weak/invalid steps.
- `src/deriv_verifier/agents/rewriter.py`: generates `suggested_rewrite` and `suggested_lemma`.
- `src/deriv_verifier/tools/__init__.py`: tools sub-package marker.
- `src/deriv_verifier/tools/latex_parser.py`: `pylatexenc`-based LaTeX → `DerivationBlock` list.
- `src/deriv_verifier/tools/sympy_check.py`: LaTeX → SymPy symbolic verification.
- `src/deriv_verifier/tools/notation_registry.py`: YAML-backed symbol registry with conflict detection.
- `src/deriv_verifier/tools/assumption_stack.py`: scoped hypothesis stack with push/pop/snapshot.
- `src/deriv_verifier/tools/hand_wave.py`: regex + phrase classifier for vague mathematical language.
- `src/deriv_verifier/tools/report_builder.py`: `StepRecord[]` → Markdown/PDF report.
- `src/deriv_verifier/loop/__init__.py`: loop sub-package marker.
- `src/deriv_verifier/loop/interactive.py`: `rich`-based per-step accept/reject/refine prompt.
- `tests/test_schemas.py`: round-trip and validation tests for all pydantic models.
- `tests/test_latex_parser.py`: unit tests for LaTeX block extraction.
- `tests/test_sympy_check.py`: unit tests for symbolic algebra/calculus checking.
- `tests/test_notation_registry.py`: unit tests for YAML registry CRUD and conflict detection.
- `tests/test_assumption_stack.py`: unit tests for stack operations and snapshots.
- `tests/test_hand_wave.py`: unit tests for hand-wave phrase detection.
- `tests/fixtures/simple_algebra.tex`: minimal algebraic derivation fixture.
- `tests/fixtures/fubini_misuse.tex`: Fubini misuse example for integration tests.
- `tests/fixtures/ot_schrodinger_bridge.tex`: OT/Schrödinger bridge derivation fixture.
- `tests/fixtures/notation_reference.yaml`: sample notation registry for test suite.
- `examples/run_on_snippet.py`: minimal demo script showing programmatic API.
- `examples/sample_derivations/`: directory for example LaTeX files.

### Notes
- Phase 0 scaffolding complete; no application logic written yet.
- Phases 1–5 implemented in single session per user instruction ("write all, run nothing").
- Decided to split `verifier` and `critic` into separate agents to keep prompts focused.
- Using `pylatexenc` over `TexSoup` for nested environment handling.
- PydanticAI chosen over LangChain for typed tool schemas and lightweight footprint.

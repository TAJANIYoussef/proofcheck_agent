# Derivation Verifier — Build Prompt for Claude Code

> **How to use this file:** Place it at the root of a new empty directory, `cd` into that directory, run `claude`, and paste: *"Read `derivation_verifier_build_prompt.md` and execute it following the build plan. Start by creating `CLAUDE.md`, `CHANGELOG.md`, and `requirements.txt`, then await confirmation before writing application code."*

---

## 1. Project Context

Build a **standalone Python CLI agent** that verifies mathematical derivations (written in LaTeX) step-by-step. The user is a PhD candidate in machine learning working on papers involving **measure theory, stochastic processes, and optimal transport** (notably a NeurIPS submission on Mixed-Type Stochastic Entropic Optimal Transport). The agent's job is to catch non-rigorous steps **before** a supervisor or reviewer does.

The agent runs **100% locally** using **Ollama** — no cloud APIs, no external LLM calls.

---

## 2. Objectives (LOCKED — do not renegotiate)

The agent must:

1. Accept a LaTeX derivation/proof (snippet or full section) as input, with optional context (paper draft, assumptions, notation file).
2. Decompose the derivation into atomic steps (one logical move per step).
3. Verify the mathematical validity of each step (algebra, calculus, probability, measure theory, OT-specific moves).
4. Detect missing or implicit assumptions (integrability, measurability, convergence, regularity, σ-finiteness, etc.).
5. Flag hand-wavy moves ("it follows that…", "clearly", unjustified limit/integral swaps, unjustified Fubini/DCT applications).
6. Check notation consistency with the surrounding paper (symbols, operators, function spaces).
7. Identify undefined objects and request/suggest definitions.
8. Suggest a more rigorous rewrite for each weak step, with the missing lemma or citation when applicable.
9. Produce a structured verification report per step: status (`valid` / `weak` / `invalid`), reason, suggested fix, confidence.
10. Support an interactive loop: user can accept, reject, or refine each flagged step before moving on.

---

## 3. Technical Stack (LOCKED)

| Dimension | Pick |
|---|---|
| Language | Python ≥ 3.11 |
| Agent framework | **PydanticAI** |
| LLM | **`gpt-oss:20b`** via **Ollama** (OpenAI-compatible endpoint at `http://localhost:11434/v1`) |
| Architecture | Linear pipeline + Critic stage |
| Pattern | Chain-of-Verification (CoVe) outer loop + ReAct inner tool calls |
| Memory | Session context + `notation.yaml` registry + assumption stack |
| CLI | `typer` + `rich` (colors, tables, prompts) |
| Output | JSON (machine) + Markdown (human) + PDF (optional via `reportlab`) |

Hardware target: 24 GB RAM laptop, Ubuntu. `gpt-oss:20b` at MXFP4 uses ~14 GB, leaving headroom for context + tools.

---

## 4. Architecture

### 4.1 Pipeline stages

```
Input (LaTeX) ─► Parse ─► Decompose ─► Verify-per-step ─► Critique ─► Rewrite/Suggest ─► Report
                                            ▲           │
                                            └──(≤2 CoVe loops)
```

Each stage is a **separate PydanticAI agent** with a typed input/output schema. Stages compose into a pipeline object that can be run end-to-end or stage-by-stage (useful for testing).

### 4.2 CoVe + ReAct

- **Outer loop (CoVe):** for each atomic step, the Verifier generates a claim → generates verification questions → answers them using tools → decides final status.
- **Inner loop (ReAct):** during verification, the agent may call SymPy, the notation registry, or the assumption stack. Max 2 internal critique rounds per step before surfacing to the user.

### 4.3 Memory layout

- **Session context (in-memory):** full derivation, current step index, per-step records.
- **`notation.yaml`** (on disk, per-project): registry of symbols — `{symbol, type, space, assumptions, first_defined_at}`.
- **Assumption stack (in-memory):** scoped stack of active hypotheses, pushed/popped as the proof enters/exits `assume`/`suppose` blocks.

### 4.4 Step record schema (the core data object)

```python
# pydantic model — define in src/schemas.py
class StepRecord(BaseModel):
    id: int                         # 1-indexed order
    raw_latex: str                  # original LaTeX for this atomic step
    claim: str                      # natural-language restatement
    justification: str | None       # what the author wrote to justify it
    status: Literal["valid", "weak", "invalid", "unchecked"]
    reason: str                     # why this status
    missing_assumptions: list[str]  # e.g. ["integrability of f", "σ-finiteness of μ"]
    hand_wave_flags: list[str]      # e.g. ["unjustified Fubini", "vague 'clearly'"]
    notation_issues: list[str]      # e.g. ["ε redefined", "M not declared"]
    suggested_rewrite: str | None
    suggested_lemma: str | None     # e.g. "Dominated Convergence Theorem"
    confidence: float               # 0.0–1.0
    cove_rounds: int                # how many internal critique rounds ran
    tools_called: list[str]         # audit trail
    user_decision: Literal["pending", "accepted", "rejected", "refined"]
```

---

## 5. Project Structure

```
derivation-verifier/
├── CLAUDE.md                   # project memory for Claude Code (see §7)
├── CHANGELOG.md                # modification log (see §7)
├── README.md                   # user-facing docs
├── requirements.txt            # pip deps (see §8)
├── pyproject.toml              # package config
├── .gitignore
├── .env.example                # OLLAMA_HOST, MODEL_NAME, etc.
│
├── src/
│   └── deriv_verifier/
│       ├── __init__.py
│       ├── cli.py              # typer entrypoint
│       ├── config.py           # pydantic-settings
│       ├── schemas.py          # StepRecord, NotationEntry, etc.
│       ├── llm.py              # Ollama client wrapper (PydanticAI Agent factory)
│       │
│       ├── agents/
│       │   ├── __init__.py
│       │   ├── parser.py       # LaTeX → structured blocks
│       │   ├── decomposer.py   # blocks → atomic steps
│       │   ├── verifier.py     # per-step CoVe verifier
│       │   ├── critic.py       # challenges verifier output
│       │   └── rewriter.py     # generates rigorous rewrite
│       │
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── latex_parser.py       # pylatexenc wrapper
│       │   ├── sympy_check.py        # symbolic algebra/calc verification
│       │   ├── notation_registry.py  # load/save/query notation.yaml
│       │   ├── assumption_stack.py   # push/pop/query assumptions
│       │   ├── hand_wave.py          # regex + LLM classifier
│       │   └── report_builder.py     # StepRecord[] → Markdown/PDF
│       │
│       ├── loop/
│       │   ├── __init__.py
│       │   └── interactive.py  # the accept/reject/refine user loop
│       │
│       └── pipeline.py         # orchestrates the stages
│
├── tests/
│   ├── test_schemas.py
│   ├── test_latex_parser.py
│   ├── test_sympy_check.py
│   ├── test_notation_registry.py
│   ├── test_assumption_stack.py
│   ├── test_hand_wave.py
│   └── fixtures/
│       ├── simple_algebra.tex
│       ├── fubini_misuse.tex
│       ├── ot_schrodinger_bridge.tex
│       └── notation_reference.yaml
│
└── examples/
    ├── run_on_snippet.py
    └── sample_derivations/
```

---

## 6. Build Plan (execute in phases — wait for user confirmation between phases)

### Phase 0 — Scaffolding (do this first, then STOP and confirm)
- Create `CLAUDE.md`, `CHANGELOG.md`, `README.md`, `requirements.txt`, `.gitignore`, `.env.example`, `pyproject.toml`.
- Create empty package skeleton (all `__init__.py` files, empty modules).
- Do NOT write any logic yet. Report back what was created.

### Phase 1 — Schemas + config
- Implement `schemas.py` (all pydantic models, `StepRecord` first).
- Implement `config.py` (reads `.env`, exposes `settings.ollama_host`, `settings.model_name`, etc.).
- Write `test_schemas.py`.

### Phase 2 — Deterministic tools (no LLM yet)
- `latex_parser.py` — given a LaTeX string, return list of blocks (equations, text, `\begin{proof}` envs, etc.).
- `notation_registry.py` — YAML load/save, `query(symbol)`, `register(symbol, ...)`, `conflict_check(...)`.
- `assumption_stack.py` — push, pop, active(), snapshot().
- `sympy_check.py` — convert simple LaTeX expressions to SymPy, check algebraic equality / limit equality / integration equality.
- `hand_wave.py` — regex pass for known phrases (list in code, configurable).
- Full unit tests for every tool.

### Phase 3 — LLM integration
- `llm.py` — build a PydanticAI `Agent` factory bound to the Ollama OpenAI-compatible endpoint.
- Test a single round-trip against `gpt-oss:20b` with a trivial structured-output call.
- Document in `CLAUDE.md` how to switch models via env var.

### Phase 4 — Agents (one at a time, test each)
- `parser.py` → thin wrapper that cleans LaTeX and hands off to `latex_parser`.
- `decomposer.py` → LLM call: blocks → `list[AtomicStep]`.
- `verifier.py` → CoVe loop per step, calls tools via ReAct, returns `StepRecord`.
- `critic.py` → second pass on weak/invalid steps.
- `rewriter.py` → produces `suggested_rewrite` and `suggested_lemma`.

### Phase 5 — Loop + CLI + report
- `interactive.py` — `rich`-based per-step prompt (accept / reject / refine / skip / quit).
- `pipeline.py` — ties everything together, supports `--non-interactive` mode.
- `cli.py` — commands: `verify <file.tex>`, `resume <session>`, `report <session>`, `notation show/add/remove`.
- `report_builder.py` — Markdown export always, PDF optional.

### Phase 6 — Integration test
- Run the agent end-to-end on `fixtures/ot_schrodinger_bridge.tex`.
- Confirm at least: decomposition works, at least one hand-wave is flagged, SymPy is called at least once, final report is generated.

---

## 7. Memory & Change Tracking Requirements (CRITICAL)

### 7.1 `CLAUDE.md` (create in Phase 0, maintain throughout)

A concise (≤ 200 lines) project-memory file. It must contain:

- **Project purpose** (one paragraph).
- **Stack** (copy §3 table).
- **Run commands**: how to set up conda env, install deps, run the CLI, run tests.
- **Coding conventions** (see §9).
- **Where things live** (one-line per top-level directory).
- **Non-obvious decisions** (e.g., "we use `pylatexenc` over `TexSoup` because it handles nested envs better").
- **Active known limitations** (a running list).

Enable Claude Code's **auto memory** to accumulate learnings automatically. When the user makes a correction during a session, add a line to `CLAUDE.md` so it persists.

### 7.2 `CHANGELOG.md` (create in Phase 0, update on every modification)

Every time you modify, create, or delete a source file during a build session, append an entry. Format:

```markdown
## [unreleased] — 2026-04-22

### Added
- `src/deriv_verifier/tools/sympy_check.py`: initial `check_equality` function.

### Changed
- `src/deriv_verifier/schemas.py`: added `cove_rounds` field to `StepRecord`.

### Fixed
- `tests/test_latex_parser.py`: handle unicode in equation environments.

### Notes
- Decided to split `verifier` and `critic` into separate agents to keep prompts small.
```

Group entries by date. Use Keep-a-Changelog-style sections (`Added` / `Changed` / `Fixed` / `Removed` / `Notes`). Do not wait until end of session — update as you go.

### 7.3 When to update what

| Event | Update |
|---|---|
| New file created | `CHANGELOG.md` (`Added`) |
| Logic changed in existing file | `CHANGELOG.md` (`Changed`) |
| Bug fixed | `CHANGELOG.md` (`Fixed`) |
| Architectural/convention decision | `CLAUDE.md` (new bullet in "Non-obvious decisions") + `CHANGELOG.md` (`Notes`) |
| Known limitation surfaces | `CLAUDE.md` ("Active known limitations") |
| User correction / preference | `CLAUDE.md` + auto memory |

---

## 8. `requirements.txt` (create in Phase 0)

```txt
# --- Core agent framework ---
pydantic>=2.8
pydantic-ai>=0.0.14
pydantic-settings>=2.4

# --- LLM client (Ollama via OpenAI-compatible endpoint) ---
openai>=1.50
ollama>=0.3.3

# --- LaTeX parsing ---
pylatexenc>=2.10

# --- Symbolic math ---
sympy>=1.13

# --- CLI + UX ---
typer>=0.12
rich>=13.7

# --- File formats ---
pyyaml>=6.0.2

# --- Reporting ---
reportlab>=4.2   # PDF export (optional but include)
markdown>=3.7

# --- Dev / test ---
pytest>=8.3
pytest-asyncio>=0.24
ruff>=0.6
mypy>=1.11
```

**Install flow the user will run** (document this in `README.md` and `CLAUDE.md`):

```bash
conda activate agentic_dev      # or: conda create -n deriv-verifier python=3.11 && conda activate deriv-verifier
pip install -r requirements.txt
ollama pull gpt-oss:20b
```

---

## 9. Coding Conventions

- **Type hints everywhere.** No implicit `Any`.
- **Pydantic models for every structured object** crossing a module boundary.
- **Small files.** If a module exceeds ~300 lines, split it.
- **No LLM calls in tools or schemas.** Tools are deterministic. LLM lives in `agents/` only.
- **Tests first** for deterministic tools (Phase 2). LLM-backed agents get integration tests with cached fixtures.
- **Logging via `logging` stdlib**, configured in `config.py`. No `print` except in `cli.py` and `interactive.py`.
- **Never commit secrets.** `.env` is gitignored; `.env.example` is committed.
- **Formatting:** `ruff` for lint and format. Line length 100.
- **Commit messages:** imperative mood, prefixed by scope (`tools(sympy): add limit check`).

---

## 10. Definition of Done (Phase 6 exit criteria)

1. `pytest` passes with ≥ 80% coverage on `tools/` and `schemas.py`.
2. `ruff check` and `mypy src/` pass with no errors.
3. `python -m deriv_verifier verify examples/sample_derivations/fubini_misuse.tex` completes end-to-end interactively.
4. `CHANGELOG.md` has entries for every phase.
5. `CLAUDE.md` is ≤ 200 lines and accurately reflects the final stack.
6. `README.md` contains setup, usage, and one worked example.

---

## 11. First Action (when the user says "go")

1. Read this file again in full.
2. Propose the exact list of files to create in Phase 0 and confirm before writing.
3. Create Phase 0 files.
4. Report back with the tree and ask for approval to proceed to Phase 1.

**Do not skip ahead. Do not generate application code in Phase 0.**

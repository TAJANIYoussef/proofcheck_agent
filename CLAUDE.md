# CLAUDE.md — Derivation Verifier Project Memory

## Project Purpose

A standalone Python CLI agent that verifies mathematical derivations (written in LaTeX)
step-by-step. Targets PhD-level rigor in measure theory, stochastic processes, and optimal
transport (specifically Mixed-Type Stochastic Entropic OT). Runs 100% locally via Ollama.
Catches non-rigorous steps before supervisors or reviewers do.

---

## Stack

| Dimension        | Pick                                                              |
|------------------|-------------------------------------------------------------------|
| Language         | Python ≥ 3.11                                                     |
| Agent framework  | PydanticAI                                                        |
| LLM              | `gpt-oss:20b` via Ollama (OpenAI-compatible at `localhost:11434`) |
| Architecture     | Linear pipeline + Critic stage                                    |
| Pattern          | Chain-of-Verification (CoVe) outer loop + ReAct inner tool calls  |
| Memory           | Session context + `notation.yaml` registry + assumption stack     |
| CLI              | `typer` + `rich`                                                  |
| Output           | JSON + Markdown + PDF (optional via `reportlab`)                  |

Hardware target: 24 GB RAM laptop, Ubuntu. `gpt-oss:20b` at MXFP4 ≈ 14 GB VRAM.

---

## Run Commands

```bash
# Environment setup
conda activate agentic_dev
# Or: conda create -n deriv-verifier python=3.11 && conda activate deriv-verifier

# Install dependencies
pip install -r requirements.txt

# Pull the model
ollama pull gpt-oss:20b

# Run the CLI
python -m deriv_verifier verify path/to/derivation.tex
python -m deriv_verifier verify path/to/derivation.tex --context paper.tex --notation notation.yaml
python -m deriv_verifier report <session-id>
python -m deriv_verifier notation show
python -m deriv_verifier notation add --symbol "\mu" --type measure --space "\\mathcal{M}(X)"

# Run tests
pytest tests/ -v
pytest tests/ --cov=src/deriv_verifier --cov-report=term-missing

# Lint + type check
ruff check src/ tests/
ruff format src/ tests/
mypy src/
```

---

## Coding Conventions

- Type hints everywhere. No implicit `Any`.
- Pydantic models for every structured object crossing a module boundary.
- Small files (≤ 300 lines). Split if larger.
- No LLM calls in tools or schemas — tools are deterministic; LLM lives in `agents/` only.
- Tests first for deterministic tools (Phase 2). LLM agents get integration tests with fixtures.
- Logging via `logging` stdlib, configured in `config.py`. No `print` except in `cli.py` and `interactive.py`.
- Never commit secrets. `.env` is gitignored; `.env.example` is committed.
- Formatting: `ruff`, line length 100.
- Commit messages: imperative mood, prefixed by scope (e.g. `tools(sympy): add limit check`).

---

## Where Things Live

- `src/deriv_verifier/` — main package
- `src/deriv_verifier/agents/` — LLM-backed pipeline stages
- `src/deriv_verifier/tools/` — deterministic tools (no LLM)
- `src/deriv_verifier/loop/` — interactive accept/reject/refine loop
- `tests/` — pytest suite
- `tests/fixtures/` — LaTeX snippets and YAML fixtures for tests
- `examples/` — runnable demo scripts and sample derivations

---

## Non-Obvious Decisions

- **`pylatexenc` over `TexSoup`**: handles nested environments (`\begin{proof}` inside
  `\begin{theorem}`) more robustly; TexSoup struggles with malformed or partial LaTeX.
- **Separate `verifier` and `critic` agents**: keeps individual prompts small and focused;
  the critic challenges the verifier's output in a second pass rather than one mega-prompt.
- **PydanticAI over LangChain**: lighter dependency footprint, typed tool call schemas out of
  the box, and direct OpenAI-compatible endpoint support makes Ollama integration trivial.
- **CoVe max 2 rounds per step**: prevents infinite loop on ambiguous steps; surfaces to user
  after 2 internal critique rounds.
- **Assumption stack (in-memory) separate from notation registry (on-disk YAML)**: assumptions
  are ephemeral per proof; notation is project-persistent and human-editable.
- **Model switchable via env var `MODEL_NAME`**: set in `.env`; no code changes needed to test
  with a different Ollama model.

---

## Active Known Limitations

- SymPy converter only handles simple algebraic/calculus LaTeX; complex measure-theoretic
  notation (e.g., Wasserstein distance, Sinkhorn divergence) is passed to LLM only.
- PDF export via `reportlab` is optional; skipped gracefully if not installed.
- The agent does not download external papers or citations; it suggests lemma names only.
- Session persistence is file-based JSON; no database backend.

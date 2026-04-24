# proof-verification-agent
 
A local CLI that verifies mathematical derivations written in LaTeX, step by step.
The agent decomposes a proof into atomic moves, checks each one for rigour,
flags hand-wavy language and missing assumptions, and produces a structured
Markdown / PDF report. Runs entirely on [Ollama](https://ollama.com/) — no
cloud API keys, no data leaving the machine.
 
> **Status:** research prototype. The deterministic pipeline (LaTeX parsing,
> SymPy checks, notation registry, assumption stack, hand-wave detection) is
> stable. The LLM stages work end-to-end but latency is dominated by the
> local model — a ~25-block derivation takes a long time on a 20B model
> running on CPU. See [Known limitations](#known-limitations).
 
---
 
## What it does
 
- **Decomposes** a LaTeX proof into a list of atomic logical steps.
- **Verifies** each step using a Chain-of-Verification (CoVe) loop with up to
  two internal rounds before surfacing a verdict.
- **Flags** missing assumptions (integrability, measurability, σ-finiteness,
  regularity, absolute continuity, …), unjustified limit/integral swaps, and
  hand-wave phrases (`clearly`, `it follows that`, `by symmetry`, …).
- **Tracks notation** consistency via a YAML symbol registry and a scoped
  assumption stack.
- **Suggests** a more rigorous rewrite and the name of the relevant theorem
  (DCT, MCT, Fubini, Kantorovich duality, Girsanov, …) for each weak step.
- **Interactive review** — accept / reject / refine each flagged step in the
  terminal; sessions can be saved and resumed.
- **Exports** a per-step Markdown report (PDF optional).
---
 
## Architecture
 
```
LaTeX  ──►  Parse  ──►  Decompose  ──►  Verify  ──►  Critique  ──►  Rewrite  ──►  Report
                            (LLM)       (CoVe+tools)   (LLM)        (LLM)       (markdown/pdf)
```
 
- **Linear pipeline + critic stage.** Each stage is a typed PydanticAI agent
  with structured output.
- **CoVe outer loop + ReAct inner tool calls.** For each atomic step, the
  verifier generates verification questions and prefers deterministic tools
  (SymPy / regex / registry lookup) over LLM answers.
- **Memory:** session context (in-memory) + `notation.yaml` registry on disk
  + scoped assumption stack.
### Code layout
 
```
src/deriv_verifier/
├── cli.py                 # typer entrypoint (verify / resume / report / notation ...)
├── config.py              # pydantic-settings (.env-driven)
├── schemas.py             # StepRecord, NotationEntry, AtomicStep, VerificationReport, ...
├── llm.py                 # PydanticAI Agent factory bound to Ollama's OpenAI endpoint
├── pipeline.py            # stage orchestrator (async)
├── agents/
│   ├── parser.py          # LaTeX cleaning → blocks
│   ├── decomposer.py      # blocks → atomic steps  (LLM)
│   ├── verifier.py        # per-step CoVe loop    (LLM + tools)
│   ├── critic.py          # second-pass challenge (LLM)
│   └── rewriter.py        # rigorous rewrite + lemma suggestion (LLM)
├── tools/
│   ├── latex_parser.py    # pylatexenc-based block extractor
│   ├── sympy_check.py     # algebra / limit / integral equality checks
│   ├── notation_registry.py  # YAML-backed symbol registry
│   ├── assumption_stack.py   # scoped hypothesis stack
│   ├── hand_wave.py       # regex + phrase classifier for vague language
│   └── report_builder.py  # StepRecord[] → Markdown / PDF
└── loop/
    └── interactive.py     # rich-based accept / reject / refine prompt
```
 
Tools are deterministic (no LLM calls). Agents are LLM-backed. Schemas cross
every module boundary.
 
---
 
## Requirements
 
- Python ≥ 3.11
- [Ollama](https://ollama.com/) installed and running locally
- A model pulled through Ollama (default: `gpt-oss:20b`, ~14 GB at MXFP4 —
  comfortable on a 24 GB machine; smaller models work but with reduced rigour)
---
 
## Install
 
```bash
# 1. Environment
conda create -n deriv-verifier python=3.12 && conda activate deriv-verifier
# (or: python -m venv .venv && source .venv/bin/activate)
 
# 2. Package (editable)
pip install -e .
 
# 3. Model
ollama pull gpt-oss:20b
 
# 4. Config
cp .env.example .env
# edit .env if Ollama runs on a non-default host
```
 
### `.env` keys
 
| Variable              | Default                  | Meaning |
|-----------------------|--------------------------|---------|
| `OLLAMA_HOST`         | `http://localhost:11434` | Ollama server URL |
| `MODEL_NAME`          | `gpt-oss:20b`            | Any model pulled via `ollama pull` |
| `MAX_COVE_ROUNDS`     | `2`                      | Max CoVe rounds per step before surfacing |
| `SESSION_DIR`         | `sessions`               | Where session state + reports are written |
| `PDF_EXPORT_ENABLED`  | `true`                   | Toggle PDF export (Markdown is always on) |
| `LOG_LEVEL`           | `INFO`                   | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
 
---
 
## Usage
 
### Verify a derivation
 
```bash
python -m deriv_verifier verify path/to/derivation.tex
```
 
Or, after `pip install -e .`:
 
```bash
deriv-verifier verify path/to/derivation.tex
```
 
Options:
 
```bash
deriv-verifier verify derivation.tex \
  --context  paper_draft.tex      # broader LaTeX context (optional)
  --notation notation.yaml         # existing notation registry (optional)
  --output   report.md             # custom report path (optional)
  --non-interactive                # skip the per-step prompt loop
```
 
The CLI prints a per-step table as it goes. At the end, the full report
lands in `sessions/` along with a JSON snapshot of the run.
 
### Resume or re-export a session
 
```bash
deriv-verifier resume  <session-id>
deriv-verifier report  <session-id> --format md        # or: --format pdf
```
 
### Manage the notation registry
 
```bash
deriv-verifier notation show
deriv-verifier notation show --filter "\mu"
 
deriv-verifier notation add \
  --symbol "\mu" --type measure \
  --space  "\mathcal{P}(\mathcal{X})" \
  --assumptions "probability,Borel"
 
deriv-verifier notation remove --symbol "\mu"
```
 
---
 
## Example
 
A short LaTeX derivation with several classic rigour failures
(`examples/sample_derivations/entropic_ot_dual.tex`) — unjustified
differentiation under the integral, a bare `clearly, by symmetry`, an
unqualified Fubini swap, and notation drift between `f, g` and `f^*, g^*`.
 
Running:
 
```bash
deriv-verifier verify examples/sample_derivations/entropic_ot_dual.tex
```
 
produces a per-step report in `sessions/` where each problematic move is
annotated with: `status` (`valid` / `weak` / `invalid`), missing assumptions,
hand-wave flags, notation issues, suggested rewrite, suggested lemma, and the
tools that were consulted. A real report from this derivation is included in
`sessions/` for reference.
 
---
 
## Tests
 
The deterministic tools are covered by unit tests:
 
```bash
pytest tests/ -v
```
 
Covered: `schemas`, `latex_parser`, `sympy_check`, `notation_registry`,
`assumption_stack`, `hand_wave`. The LLM-backed agents are exercised via
end-to-end runs on the fixtures in `tests/fixtures/` rather than unit-tested
directly.
 
---
 
## Switching models
 
Change `MODEL_NAME` in `.env`. Anything served over Ollama's OpenAI-compatible
endpoint works — `qwen3:14b`, `deepseek-r1:14b`, `gemma3:12b`, etc. Smaller
models are faster but produce noisier structured output; expect more
`output validation` retries and occasional dropped blocks.
 
---
 
## Known limitations
 
- **Latency.** The pipeline issues several LLM calls per step (decompose +
  verify + up to 2 CoVe rounds + optional critique + optional rewrite).
  On a 20B model running on CPU, a ~25-block derivation takes tens of
  minutes to hours. This is not an implementation bug — it's the cost of
  running a capable model locally. A smaller model, a GPU, or a tool-first
  redesign (see below) are all valid paths forward.
- **Over-decomposition.** The LaTeX parser is conservative and produces one
  block per equation / paragraph / environment. A short proof can yield
  20+ blocks, most of which are not real logical moves. A future version
  should filter to equation-bearing blocks before the LLM touches anything.
- **Structured-output brittleness.** PydanticAI retries when the model
  returns JSON that doesn't match the schema. Smaller Ollama models can
  exhaust retries on complex blocks; the agent logs the block index and
  moves on.
- **Hand-wave detector is regex + phrase-list.** It catches common offenders
  (`clearly`, `it follows that`, unqualified Fubini/DCT, …) but is not
  exhaustive.
- **LLM-heavy by design.** The current pipeline calls the LLM for every
  step. A tool-first refactor (SymPy / registry / regex resolve the verdict
  whenever possible; LLM only on tool-undecidable steps) is on the roadmap.
---
 
## Roadmap
 
- Tool-first verifier: only escalate to the LLM when deterministic checks
  are inconclusive.
- Parser filter: drop non-mathematical blocks before decomposition.
- Lemma database (SQLite) seeded with probability / OT classics, queried by
  the rewriter.
- Optional Lean 4 / Mathlib bridge for formal verification of critical
  steps.
- RAG over a literature corpus for citation suggestions.
---
 
## License
 
MIT
 
---
 
## Author
 
**Youssef Tajani** — PhD candidate, LIAS Laboratory, Hassan II University of
Casablanca (Faculté des Sciences Ben M'Sik).
 

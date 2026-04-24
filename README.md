# Derivation Verifier

A standalone Python CLI agent that verifies mathematical derivations (written in LaTeX)
step-by-step. Designed for PhD-level rigor in measure theory, stochastic processes, and
optimal transport. Runs 100% locally via [Ollama](https://ollama.com/) — no cloud API calls.

---

## Features

- Decomposes LaTeX proofs into atomic logical steps
- Verifies each step's mathematical validity (algebra, calculus, measure theory, OT)
- Detects missing assumptions (integrability, measurability, σ-finiteness, regularity)
- Flags hand-wavy language ("clearly", unjustified Fubini/DCT applications)
- Checks notation consistency across the derivation
- Suggests rigorous rewrites and relevant lemmas/theorems
- Interactive accept / reject / refine loop per flagged step
- Exports structured reports (Markdown and optional PDF)

---

## Setup

### Prerequisites

- Ubuntu / Linux (tested on 24 GB RAM laptop)
- [Conda](https://docs.conda.io/) or Python 3.11+
- [Ollama](https://ollama.com/) installed and running

### Install

```bash
# Activate (or create) conda environment
conda activate agentic_dev
# Or create fresh:
# conda create -n deriv-verifier python=3.11 && conda activate deriv-verifier

# Install Python dependencies
pip install -r requirements.txt

# Pull the model (≈14 GB at MXFP4 — ensure enough disk space)
ollama pull gpt-oss:20b

# Copy and edit environment config
cp .env.example .env
# Edit .env if Ollama runs on a non-default host/port
```

---

## Usage

### Verify a derivation

```bash
# Basic verification
python -m deriv_verifier verify path/to/derivation.tex

# With paper context and notation registry
python -m deriv_verifier verify derivation.tex \
    --context paper_draft.tex \
    --notation notation.yaml \
    --output report.md

# Non-interactive mode (batch, no prompts)
python -m deriv_verifier verify derivation.tex --non-interactive
```

### Resume or report a session

```bash
python -m deriv_verifier resume <session-id>
python -m deriv_verifier report <session-id> --format pdf
```

### Manage the notation registry

```bash
python -m deriv_verifier notation show
python -m deriv_verifier notation show --filter "\mu"
python -m deriv_verifier notation add --symbol "\mu" --type measure \
    --space "\mathcal{M}(X)" --assumptions "sigma-finite"
python -m deriv_verifier notation remove --symbol "\mu"
```

---

## Worked Example

Given a LaTeX snippet that unjustifiably swaps integral and limit:

```latex
\begin{proof}
Let $f_n \to f$ pointwise. Then
\[
  \lim_{n\to\infty} \int f_n \, d\mu = \int \lim_{n\to\infty} f_n \, d\mu = \int f \, d\mu.
\]
It clearly follows that $\int f \, d\mu < \infty$.
\end{proof}
```

The agent will:
1. Decompose into 3 atomic steps.
2. Flag Step 1 (`lim ∫ = ∫ lim`) as **weak** — missing DCT/MCT hypothesis.
3. Flag Step 2 ("clearly follows") as **weak** — unjustified finiteness claim.
4. Suggest: "By the Dominated Convergence Theorem (if |f_n| ≤ g ∈ L¹(μ))..."
5. Output a structured Markdown report.

---

## Running Tests

```bash
pytest tests/ -v
pytest tests/ --cov=src/deriv_verifier --cov-report=term-missing
```

---

## Project Structure

```
src/deriv_verifier/
├── cli.py              # typer entrypoint
├── config.py           # pydantic-settings
├── schemas.py          # StepRecord, NotationEntry, etc.
├── llm.py              # Ollama/PydanticAI agent factory
├── pipeline.py         # stage orchestrator
├── agents/             # LLM-backed pipeline stages
├── tools/              # deterministic tools (no LLM)
└── loop/               # interactive prompt loop
```

---

## Switching Models

Set `MODEL_NAME` in your `.env` file:

```bash
MODEL_NAME=llama3.1:8b   # lighter, faster, less accurate
MODEL_NAME=gpt-oss:20b   # default — recommended
```

---

## License

MIT

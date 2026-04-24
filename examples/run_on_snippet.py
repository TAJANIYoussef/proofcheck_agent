"""Minimal demo: run the verifier on an inline LaTeX snippet.

Usage:
    python examples/run_on_snippet.py

Requires Ollama running locally with the model configured in .env.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure the package is importable from the repo root
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from deriv_verifier.config import settings
from deriv_verifier.pipeline import run_pipeline

SNIPPET = r"""
\begin{proof}
Let $f_n \to f$ pointwise on $(X, \mathcal{B}(X), \mu)$.
Then
\[
  \lim_{n\to\infty} \int_X f_n \, d\mu = \int_X f \, d\mu.
\]
It clearly follows that $\int_X f \, d\mu < \infty$.
\end{proof}
"""


async def main() -> None:
    settings.configure_logging()

    # Write snippet to a temp file
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".tex", delete=False) as f:
        f.write(SNIPPET)
        tmp_path = Path(f.name)

    print(f"Verifying snippet in {tmp_path} …\n")

    report = await run_pipeline(
        source_file=tmp_path,
        non_interactive=True,
        output_file=Path("snippet_report.md"),
    )

    print(f"\nSession: {report.session_id}")
    print(f"Total steps: {report.total_steps}")
    print(f"Valid: {report.valid_count}  Weak: {report.weak_count}  Invalid: {report.invalid_count}")
    print("\nReport written to: snippet_report.md")

    tmp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    asyncio.run(main())

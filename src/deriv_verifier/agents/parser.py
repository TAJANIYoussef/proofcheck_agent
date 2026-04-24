"""Parser agent: clean LaTeX input and produce a list of DerivationBlocks.

This is a thin wrapper around the deterministic ``latex_parser`` tool.
It normalises the input (strips preamble, normalises whitespace) before
handing off to the tool — no LLM call needed at this stage.
"""

from __future__ import annotations

import logging
import re

from deriv_verifier.schemas import DerivationBlock
from deriv_verifier.tools.latex_parser import parse_latex

logger = logging.getLogger(__name__)

# Patterns that mark document-level preamble (discard before \begin{document})
_DOCUMENT_BEGIN_RE = re.compile(r"\\begin\{document\}", re.IGNORECASE)
_DOCUMENT_END_RE = re.compile(r"\\end\{document\}", re.IGNORECASE)


def parse(source: str) -> list[DerivationBlock]:
    """Clean *source* LaTeX and return a structured block list.

    If ``\\begin{document}`` is present the preamble and postamble are
    stripped so the parser only sees the document body.
    """
    body = _extract_body(source)
    body = _strip_comments(body)
    blocks = parse_latex(body)
    logger.info("Parser produced %d block(s).", len(blocks))
    return blocks


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_body(source: str) -> str:
    """Return only the content between \\begin{document} … \\end{document}.

    If no \\begin{document} is found, return the source unchanged.
    """
    begin_match = _DOCUMENT_BEGIN_RE.search(source)
    if begin_match is None:
        return source
    start = begin_match.end()

    end_match = _DOCUMENT_END_RE.search(source, start)
    end = end_match.start() if end_match else len(source)
    return source[start:end]


def _strip_comments(source: str) -> str:
    """Remove LaTeX line comments (% …) from *source*."""
    # Keep lines that start with % as section separators but strip inline comments.
    # A % that is preceded by \ is escaped and must be kept.
    return re.sub(r"(?<!\\)%[^\n]*", "", source)

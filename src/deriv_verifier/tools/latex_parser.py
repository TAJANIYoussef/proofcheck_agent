"""LaTeX → DerivationBlock list using pylatexenc.

Deterministic — no LLM calls.
"""

from __future__ import annotations

import logging
import re

from pylatexenc.latexwalker import (
    LatexCharsNode,
    LatexCommentNode,
    LatexEnvironmentNode,
    LatexGroupNode,
    LatexMacroNode,
    LatexMathNode,
    LatexNode,
    LatexWalker,
)

from deriv_verifier.schemas import BlockKind, DerivationBlock

logger = logging.getLogger(__name__)

# Environments that map to specific BlockKinds
_ENV_KIND_MAP: dict[str, BlockKind] = {
    "proof": BlockKind.PROOF,
    "theorem": BlockKind.THEOREM,
    "thm": BlockKind.THEOREM,
    "lemma": BlockKind.LEMMA,
    "lem": BlockKind.LEMMA,
    "definition": BlockKind.DEFINITION,
    "defn": BlockKind.DEFINITION,
    "def": BlockKind.DEFINITION,
    "remark": BlockKind.REMARK,
    "rem": BlockKind.REMARK,
    "assumption": BlockKind.ASSUMPTION,
    "equation": BlockKind.EQUATION,
    "equation*": BlockKind.EQUATION,
    "align": BlockKind.EQUATION,
    "align*": BlockKind.EQUATION,
    "gather": BlockKind.EQUATION,
    "gather*": BlockKind.EQUATION,
    "multline": BlockKind.EQUATION,
    "multline*": BlockKind.EQUATION,
    "eqnarray": BlockKind.EQUATION,
    "eqnarray*": BlockKind.EQUATION,
}

# Inline/display math delimiters as simple regex patterns
_DISPLAY_MATH_RE = re.compile(
    r"(\\\[.*?\\\]|\$\$.*?\$\$)", re.DOTALL
)


def parse_latex(source: str) -> list[DerivationBlock]:
    """Parse *source* LaTeX and return a flat list of :class:`DerivationBlock`.

    Blocks are returned in document order.  The function attempts to use
    ``pylatexenc`` for structured parsing; if that fails it falls back to a
    regex-based splitter so the pipeline never hard-stops on malformed input.
    """
    source = _normalise_whitespace(source)
    try:
        return _parse_with_latexwalker(source)
    except Exception as exc:  # noqa: BLE001
        logger.warning("pylatexenc parse failed (%s); using regex fallback", exc)
        return _parse_with_regex_fallback(source)


# ---------------------------------------------------------------------------
# Primary parser (pylatexenc)
# ---------------------------------------------------------------------------


def _parse_with_latexwalker(source: str) -> list[DerivationBlock]:
    walker = LatexWalker(source)
    nodelist, _, _ = walker.get_latex_nodes(pos=0)
    blocks: list[DerivationBlock] = []
    _visit_nodelist(nodelist, blocks, source)
    return _merge_adjacent_text(blocks)


def _visit_nodelist(
    nodes: list[LatexNode],
    blocks: list[DerivationBlock],
    source: str,
) -> None:
    for node in nodes:
        _visit_node(node, blocks, source)


def _visit_node(node: LatexNode, blocks: list[DerivationBlock], source: str) -> None:
    idx = len(blocks)

    if isinstance(node, LatexEnvironmentNode):
        env_name: str = node.environmentname
        kind = _ENV_KIND_MAP.get(env_name, BlockKind.OTHER)
        raw = source[node.pos : node.pos + node.len] if node.len else node.latex_verbatim()
        blocks.append(
            DerivationBlock(
                index=idx,
                kind=kind,
                raw_latex=raw.strip(),
                environment=env_name,
            )
        )

    elif isinstance(node, LatexMathNode):
        raw = source[node.pos : node.pos + node.len] if node.len else node.latex_verbatim()
        blocks.append(
            DerivationBlock(index=idx, kind=BlockKind.EQUATION, raw_latex=raw.strip())
        )

    elif isinstance(node, LatexGroupNode):
        _visit_nodelist(node.nodelist, blocks, source)

    elif isinstance(node, (LatexCharsNode, LatexMacroNode)):
        raw = source[node.pos : node.pos + node.len] if node.len else node.latex_verbatim()
        text = raw.strip()
        if text:
            blocks.append(DerivationBlock(index=idx, kind=BlockKind.TEXT, raw_latex=text))

    elif isinstance(node, LatexCommentNode):
        pass  # skip comments

    else:
        if hasattr(node, "len") and node.len:
            raw = source[node.pos : node.pos + node.len].strip()
            if raw:
                blocks.append(DerivationBlock(index=idx, kind=BlockKind.OTHER, raw_latex=raw))


# ---------------------------------------------------------------------------
# Fallback parser (regex-based)
# ---------------------------------------------------------------------------


def _parse_with_regex_fallback(source: str) -> list[DerivationBlock]:
    """Split on known environments and math delimiters; treat the rest as text."""
    blocks: list[DerivationBlock] = []
    env_re = re.compile(
        r"(\\begin\{([^}]+)\}.*?\\end\{\2\})",
        re.DOTALL,
    )
    display_re = re.compile(r"(\\\[.*?\\\]|\$\$.*?\$\$)", re.DOTALL)
    combined = re.compile(
        r"(\\begin\{([^}]+)\}.*?\\end\{\2\}|\\\[.*?\\\]|\$\$.*?\$\$)",
        re.DOTALL,
    )

    pos = 0
    for m in combined.finditer(source):
        # text before match
        pre = source[pos : m.start()].strip()
        if pre:
            blocks.append(
                DerivationBlock(
                    index=len(blocks), kind=BlockKind.TEXT, raw_latex=pre
                )
            )

        matched_text = m.group(0)
        env_match = env_re.match(matched_text)
        if env_match:
            env_name = env_match.group(2)
            kind = _ENV_KIND_MAP.get(env_name, BlockKind.OTHER)
            blocks.append(
                DerivationBlock(
                    index=len(blocks),
                    kind=kind,
                    raw_latex=matched_text.strip(),
                    environment=env_name,
                )
            )
        else:
            blocks.append(
                DerivationBlock(
                    index=len(blocks),
                    kind=BlockKind.EQUATION,
                    raw_latex=matched_text.strip(),
                )
            )
        pos = m.end()

    # trailing text
    tail = source[pos:].strip()
    if tail:
        blocks.append(DerivationBlock(index=len(blocks), kind=BlockKind.TEXT, raw_latex=tail))

    return blocks


# ---------------------------------------------------------------------------
# Post-processing helpers
# ---------------------------------------------------------------------------


def _merge_adjacent_text(blocks: list[DerivationBlock]) -> list[DerivationBlock]:
    """Merge consecutive TEXT blocks into one to reduce noise."""
    if not blocks:
        return blocks
    merged: list[DerivationBlock] = []
    acc: DerivationBlock | None = None
    for block in blocks:
        if block.kind == BlockKind.TEXT:
            if acc is None:
                acc = block.model_copy()
            else:
                acc = acc.model_copy(
                    update={"raw_latex": acc.raw_latex + " " + block.raw_latex}
                )
        else:
            if acc is not None:
                merged.append(acc)
                acc = None
            merged.append(block)
    if acc is not None:
        merged.append(acc)
    # Re-index
    return [b.model_copy(update={"index": i}) for i, b in enumerate(merged)]


def _normalise_whitespace(source: str) -> str:
    # Collapse multiple blank lines to a single blank line
    return re.sub(r"\n{3,}", "\n\n", source)


# ---------------------------------------------------------------------------
# Utility: extract raw equation strings only
# ---------------------------------------------------------------------------


def extract_equations(source: str) -> list[str]:
    """Convenience function: return just the raw LaTeX of equation blocks."""
    blocks = parse_latex(source)
    return [b.raw_latex for b in blocks if b.kind == BlockKind.EQUATION]

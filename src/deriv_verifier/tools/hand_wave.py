"""Hand-wave detector: regex + phrase classifier for vague mathematical language.

Deterministic — no LLM calls.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class HandWaveFlag:
    """A single detected hand-wave in a LaTeX string."""

    phrase: str
    category: str
    position: int  # character offset in the source string
    context: str   # surrounding text (±40 chars)
    severity: str  # "high" | "medium" | "low"


# ---------------------------------------------------------------------------
# Phrase database
# ---------------------------------------------------------------------------

# Each entry: (pattern, category, severity)
_PATTERNS: list[tuple[str, str, str]] = [
    # Vague certainty
    (r"\bclearly\b", "vague_certainty", "high"),
    (r"\bobviously\b", "vague_certainty", "high"),
    (r"\bit is easy to see\b", "vague_certainty", "high"),
    (r"\bit follows (easily |immediately |trivially )?that\b", "vague_certainty", "high"),
    (r"\bone can easily (show|verify|check|see)\b", "vague_certainty", "high"),
    (r"\btrivially\b", "vague_certainty", "medium"),
    (r"\bwe (can |may |could )?easily\b", "vague_certainty", "medium"),
    (r"\bstraightforward(ly)?\b", "vague_certainty", "low"),
    (r"\bby inspection\b", "vague_certainty", "medium"),
    (r"\bby routine calculation\b", "vague_certainty", "low"),
    # Unjustified analysis moves
    (r"\bit is (well[- ]known|known) that\b", "missing_citation", "medium"),
    (r"\bstandard arguments? (show|give|yield)\b", "missing_citation", "medium"),
    (r"\ba (standard|routine|classical) argument\b", "missing_citation", "medium"),
    (r"\bby a (standard|routine) (calculation|argument|computation)\b", "missing_citation", "low"),
    # Unjustified limit/integral swaps
    (r"(swap(ping)?|interchang(e|ing)|commu(ting|te))\s+(limit|sum|integral|expectation)",
     "unjustified_interchange", "high"),
    (r"(limit|sum|integral|expectation)\s+(and|,)\s+(limit|sum|integral|expectation)\s+"
     r"(can be swapped|may be interchanged|commute)", "unjustified_interchange", "high"),
    (r"\\lim.*\\int|\\int.*\\lim", "unjustified_interchange", "high"),
    # Fubini / Tonelli without hypothesis
    (r"\bfubini'?s?\b(?!.*theorem.*(\bintegrab|\bsigma.?finite|\bnon.?negative))",
     "unjustified_fubini", "high"),
    (r"\btonelli'?s?\b", "unjustified_fubini", "medium"),
    (r"\bby fubini\b", "unjustified_fubini", "high"),
    # DCT / MCT without hypothesis
    (r"\bdominated convergence\b(?!.*theorem.*(\bdominated|\bg\s*\\in))",
     "unjustified_dct", "high"),
    (r"\bmonotone convergence\b(?!.*theorem)", "unjustified_mct", "high"),
    (r"\bby (the )?(dct|mct)\b", "unjustified_dct_mct", "high"),
    # Missing measurability / integrability claims
    (r"\bintegrab(le|ility)\b.*\bassume(d|s)?\b", "assumed_integrability", "medium"),
    (r"\bwe may assume\b", "unjustified_assumption", "medium"),
    (r"\bwithout loss of generality\b", "wlog_unchecked", "low"),
    (r"\bwlog\b", "wlog_unchecked", "low"),
    # Vague existence / uniqueness
    (r"\bthere exists (a |an |some )?(unique )?(such )?\b.*\bsince\b",
     "unjustified_existence", "medium"),
    (r"\buniqueness follows\b", "unjustified_uniqueness", "medium"),
    # Handwavy limits
    (r"\bas\s+[a-zA-Z]\s*(\\to|→|->)\s*(\\infty|∞|\d+)\s*,?\s*(we (get|have|obtain)|this gives)",
     "unjustified_limit", "medium"),
    # Compactness arguments without justification
    (r"\bby compactness\b", "unjustified_compactness", "medium"),
    (r"\bthe (sequence|net) (has |admits )?(a )?convergent sub(sequence|net)\b",
     "unjustified_compactness", "medium"),
]


_COMPILED: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(pattern, re.IGNORECASE | re.DOTALL), category, severity)
    for pattern, category, severity in _PATTERNS
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_hand_waves(source: str) -> list[HandWaveFlag]:
    """Return all hand-wave phrases found in *source*.

    Scans the plain-text content of *source* (LaTeX stripped to text first
    for phrase matching, but reports character positions in the original).
    """
    flags: list[HandWaveFlag] = []
    # Work on the original string for position accuracy
    seen_spans: set[tuple[int, int]] = set()
    for pattern, category, severity in _COMPILED:
        for m in pattern.finditer(source):
            span = (m.start(), m.end())
            if span in seen_spans:
                continue
            seen_spans.add(span)
            start = max(0, m.start() - 40)
            end = min(len(source), m.end() + 40)
            flags.append(
                HandWaveFlag(
                    phrase=m.group(0),
                    category=category,
                    position=m.start(),
                    context=source[start:end],
                    severity=severity,
                )
            )
    flags.sort(key=lambda f: f.position)
    logger.debug("Detected %d hand-wave flag(s).", len(flags))
    return flags


def summarise_flags(flags: list[HandWaveFlag]) -> list[str]:
    """Convert a list of HandWaveFlag to human-readable strings."""
    return [
        f"[{f.severity.upper()}] '{f.phrase}' ({f.category}) near: '…{f.context.strip()}…'"
        for f in flags
    ]


def has_high_severity_flags(flags: list[HandWaveFlag]) -> bool:
    return any(f.severity == "high" for f in flags)

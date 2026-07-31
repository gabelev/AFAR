"""Display shim for the pre-voice-fix corpus — Python mirror of
web/lib/normalize-act-names.mjs (one-to-one; the vitest cases over there and
kernel/tests/test_display.py here pin the same behavior).

The first logged sets (releases 0002-0004) address the acts by internal id
("Rust", "Keep", "Silt") because the kernel didn't know the stage names yet
(fixed in PR #20 — personas now first-name each other: Delta / Roan / Evers).
The append-only log is never edited; display surfaces normalize internal act
ids used as PROPER NOUNS in quoted generated text to first names:

  - CAPITALIZED, word-boundary matches only: "Rust"->"Roan", "Keep"->"Evers",
    "Silt"->"Delta". Possessives carry over ("Rust's"->"Roan's").
  - Common-noun/verb uses are lowercase in the corpus ("under enough silt to
    hold weight", "keep the hum") and are NEVER touched.
  - Ambiguous capitalized uses are handled by the curated EXCEPTIONS list,
    not heuristics — every substitution in the shipped corpus was
    human-reviewed (none were needed; see DECISIONS.md 2026-07-31).

Future runs speak first names already, so on post-fix text this is a no-op.
"""

from __future__ import annotations

import re

# Internal act id -> the first name the acts use for each other.
ACT_FIRST_NAMES = {"silt": "Delta", "rust": "Roan", "keep": "Evers"}

_NAME_BY_ID_CAP = {"Rust": "Roan", "Keep": "Evers", "Silt": "Delta"}

# Exact phrases (case-sensitive) inside which a capitalized act id is NOT a
# proper-noun reference to the act. Currently empty — kept in lockstep with
# EXCEPTIONS in web/lib/normalize-act-names.mjs.
EXCEPTIONS: list[str] = []

_PATTERN = re.compile(r"\b(Rust|Keep|Silt)(['’]s)?\b")


def normalize_act_names(text: str) -> str:
    """Normalize internal act ids used as proper nouns in quoted generated
    text to the acts' first names. Lowercase uses are never touched."""
    if not isinstance(text, str) or not text:
        return text
    spans = _exception_spans(text)

    def repl(match: re.Match[str]) -> str:
        if any(start <= match.start() < end for start, end in spans):
            return match.group(0)
        return _NAME_BY_ID_CAP[match.group(1)] + (match.group(2) or "")

    return _PATTERN.sub(repl, text)


def _exception_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for phrase in EXCEPTIONS:
        start = text.find(phrase)
        while start != -1:
            spans.append((start, start + len(phrase)))
            start = text.find(phrase, start + len(phrase))
    return spans

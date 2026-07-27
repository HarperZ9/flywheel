#!/usr/bin/env python3
"""writing_readability.py -- the Flesch dial, reported and never gated.

Standard library only.
"""
from __future__ import annotations

import re

# Copied from check_writing.WORD_RE, not imported: importing it back would be
# circular (check_writing imports reading_ease/syllables from here). This
# module's copy is deliberate; check_writing stays the source of truth for
# word tokenization.
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]*")
# Copied from check_writing._SENT, same reason as _WORD_RE above; check_writing
# stays the source of truth for prose splitting.
_SENT = re.compile(r"(?<=[.!?])(?=\s|$)")
_VOWEL_GROUP = re.compile(r"[aeiouy]+")


def _sentences(text: str) -> list[str]:
    out = []
    for chunk in _SENT.split(text):
        collapsed = " ".join(chunk.split())
        if collapsed:
            out.append(collapsed)
    return out


def syllables(word: str) -> int:
    """Count syllables in a word using vowel groups and heuristics.

    Used for Flesch readability ease calculation. Returns at least 1.
    """
    w = word.lower().strip("'-")
    if not w:
        return 0
    n = len(_VOWEL_GROUP.findall(w))
    if w.endswith("e") and n > 1 and not w.endswith(("le", "ee")):
        n -= 1
    return max(1, n)


def reading_ease(text: str) -> "float | None":
    """Flesch reading ease over stripped prose; None under 30 words.

    A crude dial, reported and never gated: the spec calls the formula crude
    and the per-word syllable count here is a heuristic on top of that.
    """
    words = _WORD_RE.findall(text)
    sents = _sentences(text)
    if len(words) < 30 or not sents:
        return None
    syl = sum(syllables(w) for w in words)
    return round(206.835 - 1.015 * (len(words) / len(sents))
                 - 84.6 * (syl / len(words)), 1)

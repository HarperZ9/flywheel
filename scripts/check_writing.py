#!/usr/bin/env python3
"""check_writing.py -- score prose against a register profile.

A sibling of check_claim_language.py. It reads a profile from writing_profiles,
counts violations per 100 words, and reports the delta between two drafts, since
the delta is the signal. It scores the FORM of prose only. A low score is not a
true document and is not proof of anything, and this tool never tries to defeat
AI detection.

Standard library only.
"""
from __future__ import annotations

import re

WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]*")
_FENCE = re.compile(r"```.*?```", re.DOTALL)
_INLINE = re.compile(r"`[^`]*`")
_MATHBLOCK = re.compile(r"\$\$.*?\$\$", re.DOTALL)
_MATH = re.compile(r"\$[^$\n]*\$")
_SENT = re.compile(r"(?<=[.!?])(?=\s|$)")


def strip_code(text: str) -> str:
    text = _FENCE.sub(" ", text)
    text = _MATHBLOCK.sub(" ", text)
    text = _INLINE.sub(" ", text)
    text = _MATH.sub(" ", text)
    return text


def sentences(text: str) -> list[str]:
    out = []
    for chunk in _SENT.split(text):
        collapsed = " ".join(chunk.split())
        if collapsed:
            out.append(collapsed)
    return out


def count_words(text: str) -> int:
    return len(WORD_RE.findall(text))

"""Compatibility module for harness.writing_lint.check_writing."""

from __future__ import annotations

from .check_writing import (
    BANNED,
    BE,
    DOES_NOT_PROVE,
    HARD_BY_SLOP,
    HARD_DEFAULTS,
    HEDGE_WORDS,
    KNOWN_CATEGORIES,
    MARKETING,
    MODAL_HEDGE,
    PHRASAL,
    REPORT_ONLY,
    WORD_RE,
    _ING_MAIN,
    _NOMINAL,
    _PASSIVE,
    _SENT,
    check_text,
    count_words,
    delta,
    main,
    paragraphs,
    reading_ease,
    score_file,
    sentences,
    strip_code,
    syllables,
)

__all__ = [
    "BANNED",
    "BE",
    "DOES_NOT_PROVE",
    "HARD_BY_SLOP",
    "HARD_DEFAULTS",
    "HEDGE_WORDS",
    "KNOWN_CATEGORIES",
    "MARKETING",
    "MODAL_HEDGE",
    "PHRASAL",
    "REPORT_ONLY",
    "WORD_RE",
    "_ING_MAIN",
    "_NOMINAL",
    "_PASSIVE",
    "_SENT",
    "check_text",
    "count_words",
    "delta",
    "main",
    "paragraphs",
    "reading_ease",
    "score_file",
    "sentences",
    "strip_code",
    "syllables",
]

if __name__ == "__main__":
    raise SystemExit(main())

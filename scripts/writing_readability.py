#!/usr/bin/env python3
"""Backward-compatible import shim for harness.writing_lint.readability."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.writing_lint.readability import (  # noqa: E402
    _SENT,
    _WORD_RE,
    _sentences,
    reading_ease,
    syllables,
)

__all__ = ["_SENT", "_WORD_RE", "_sentences", "reading_ease", "syllables"]

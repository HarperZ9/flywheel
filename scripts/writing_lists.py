#!/usr/bin/env python3
"""Backward-compatible import shim for harness.writing_lint.lists."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.writing_lint.lists import (  # noqa: E402
    BANNED,
    HARD_DEFAULTS,
    HEDGE_WORDS,
    ING_MAIN,
    KNOWN_CATEGORIES,
    MARKETING,
    MODAL_HEDGE,
    NOMINAL,
    PASSIVE,
    PHRASAL,
    REPORT_ONLY_CATEGORIES,
)

__all__ = [
    "BANNED",
    "HARD_DEFAULTS",
    "HEDGE_WORDS",
    "ING_MAIN",
    "KNOWN_CATEGORIES",
    "MARKETING",
    "MODAL_HEDGE",
    "NOMINAL",
    "PASSIVE",
    "PHRASAL",
    "REPORT_ONLY_CATEGORIES",
]

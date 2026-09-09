#!/usr/bin/env python3
"""Backward-compatible import shim for harness.writing_lint.profiles."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.writing_lint.profiles import (  # noqa: E402
    DEFAULT,
    PATH_RULES,
    PROFILES,
    SCHEMA_FIELDS,
    ProfileError,
    declared_profile,
    load,
    profile_for,
)

__all__ = [
    "DEFAULT",
    "PATH_RULES",
    "PROFILES",
    "SCHEMA_FIELDS",
    "ProfileError",
    "declared_profile",
    "load",
    "profile_for",
]

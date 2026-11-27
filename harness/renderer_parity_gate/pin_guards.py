# SPDX-License-Identifier: MIT
"""Strict numeric, FNV-1a 64-bit hex pin, and canonical SHA-256 guards.

Provides fail-closed validation helpers for the Flywheel renderer parity gate.
Rejects booleans disguised as ints, IEEE-754 NaN/Inf values, malformed FNV-1a
hex strings, and non-zero ULP errors.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

HONEST_SCOPE_LIMIT = (
    "Validates scalar bounds (strict int, finite float, non-bool), 64-bit "
    "FNV-1a hex formatting, and canonical JSON SHA-256 digests in pure Python "
    "stdlib. Does not compile C++23 or BuildLang sources."
)

FNV1A_64_RE = re.compile(r"^0x[0-9a-fA-F]{16}$")


def is_strict_int(value: Any) -> bool:
    """Return True iff value is an int and not a bool."""
    return isinstance(value, int) and not isinstance(value, bool)


def is_strict_finite_float(value: Any) -> bool:
    """Return True iff value is a finite real int/float and not a bool."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


def parse_strict_positive_int(raw: Any, label: str) -> tuple[int | None, str | None]:
    """Parse a strictly positive integer from int or ASCII digit string."""
    if is_strict_int(raw):
        return (raw, None) if raw > 0 else (None, f"{label}: must be > 0")
    if isinstance(raw, str):
        text = raw.strip()
        if text.isdigit():
            val = int(text)
            if val > 0:
                return val, None
        return None, f"{label}: invalid positive int {raw!r}"
    return None, f"{label}: unsupported type {type(raw).__name__}"


def parse_strict_ulp(raw: Any, label: str) -> tuple[float | None, str | None]:
    """Parse a finite non-negative ULP error (rejecting bool/NaN/Inf)."""
    if isinstance(raw, bool):
        return None, f"{label}: boolean ULP rejected"
    if isinstance(raw, (int, float)):
        val = float(raw)
        if not math.isfinite(val) or val < 0.0:
            return None, f"{label}: invalid ULP {raw!r}"
        return val, None
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None, f"{label}: empty ULP"
        try:
            val = float(text)
        except ValueError:
            return None, f"{label}: unparseable ULP {raw!r}"
        if not math.isfinite(val) or val < 0.0:
            return None, f"{label}: non-finite or negative ULP {raw!r}"
        return val, None
    return None, f"{label}: unsupported ULP type {type(raw).__name__}"


def normalize_fnv1a_pin(raw: Any, label: str) -> tuple[str | None, str | None]:
    """Validate and lowercase a non-zero 64-bit FNV-1a hex pin."""
    if not isinstance(raw, str):
        return None, f"{label}: FNV-1a pin must be a hex string"
    pin = raw.strip().lower()
    if not FNV1A_64_RE.match(pin):
        return None, f"{label}: malformed 64-bit FNV-1a pin {raw!r}"
    if pin == "0x0000000000000000":
        return None, f"{label}: zero FNV-1a pin rejected"
    return pin, None


def parse_strict_flag_01(raw: Any, label: str) -> tuple[int | None, str | None]:
    """Parse a strict binary flag 0 or 1 (rejecting bool/NaN/Inf)."""
    if isinstance(raw, bool):
        return None, f"{label}: boolean flag rejected (use 0 or 1)"
    if isinstance(raw, int):
        return (raw, None) if raw in (0, 1) else (None, f"{label}: expected 0 or 1")
    if isinstance(raw, str) and raw.strip() in ("0", "1"):
        return int(raw.strip()), None
    return None, f"{label}: invalid 0/1 flag {raw!r}"


def canonical_sha256_hex(payload: Any) -> str:
    """Compute a deterministic SHA-256 hex digest over canonical JSON."""
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

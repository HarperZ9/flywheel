# SPDX-License-Identifier: MIT
"""Strict IEEE-754 finite-float, strict-int, and canonical hashing guards.

Provides reusable fail-closed numeric and hashing primitives for the Flywheel
surpass matrix oracle. Rejects booleans disguised as ints, NaN/Inf floats, and
non-positive identifiers.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

HONEST_SCOPE_LIMIT = (
    "Validates Python scalar types (strict int, finite float, non-bool) and "
    "deterministic SHA-256 canonical JSON digests only. Does not validate "
    "external filesystem permissions or remote database integrity."
)


def is_strict_int(value: Any) -> bool:
    """Return True iff value is an int and not a bool."""
    return isinstance(value, int) and not isinstance(value, bool)


def is_strict_finite_float(value: Any) -> bool:
    """Return True iff value is a real int/float (not bool) and finite."""
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


def parse_strict_positive_int(value: Any) -> int | None:
    """Parse a positive strict integer from int or ASCII digit string."""
    if is_strict_int(value):
        return value if value > 0 else None
    if isinstance(value, str):
        raw = value.strip()
        if raw.isdigit():
            parsed = int(raw)
            return parsed if parsed > 0 else None
    return None


def validate_percentage(value: Any, label: str) -> list[str]:
    """Validate that value is a finite number in [0.0, 100.0]."""
    if not is_strict_finite_float(value):
        return [f"{label}: non-finite or invalid percentage {value!r}"]
    num = float(value)
    if num < 0.0 or num > 100.0:
        return [f"{label}: percentage {num} out of [0.0, 100.0]"]
    return []


def validate_catalogue_id_list(
    raw_ids: Any,
    label: str,
) -> tuple[list[int], list[str]]:
    """Validate a list of strict positive integer catalogue IDs."""
    if not isinstance(raw_ids, list):
        return [], [f"{label}: catalogue IDs must be a list"]
    parsed: list[int] = []
    errors: list[str] = []
    for idx, item in enumerate(raw_ids):
        if not is_strict_int(item) or item <= 0:
            errors.append(f"{label}[{idx}]: invalid catalogue_id {item!r}")
        else:
            parsed.append(item)
    return parsed, errors


def canonical_sha256_hex(payload: Any) -> str:
    """Compute a deterministic SHA-256 hex digest over canonical JSON."""
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def sha256_bytes_hex(data: bytes) -> str:
    """Compute a SHA-256 hex digest over raw bytes."""
    return hashlib.sha256(data).hexdigest()

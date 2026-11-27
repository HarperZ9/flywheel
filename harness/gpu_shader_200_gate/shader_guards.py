# SPDX-License-Identifier: MIT
"""Strict numeric, SHA-256, and validator guards for gpu_shader_200_gate.

Provides pure-stdlib fail-closed scalar, digest, and validator-marker checks
for the 200-shader 5-backend GPU compute manifest.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

HONEST_SCOPE_LIMIT = (
    "Validates 5 GPU backend names, 64-hex SHA-256 digests, strict non-bool "
    "integers, finite float bounds, and validator pass markers in pure Python "
    "stdlib. Does not invoke dxc, glslangValidator, spirv-val, or naga."
)

REQUIRED_GPU_TARGETS: frozenset[str] = frozenset(
    {"wgsl", "hlsl", "msl", "spirv", "glsl"}
)

SHA256_HEX_RE = re.compile(r"^[0-9a-fA-F]{64}$")
FAIL_TOKEN_RE = re.compile(r"\b(?:FAIL|ERROR|REJECT|INVALID)\b", re.I)


def is_strict_int(value: Any) -> bool:
    """Return True iff value is an int and not a bool."""
    return isinstance(value, int) and not isinstance(value, bool)


def is_strict_finite_float(value: Any) -> bool:
    """Return True iff value is a finite real int/float and not a bool."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


def normalize_sha256(raw: Any, label: str) -> tuple[str | None, str | None]:
    """Validate and lowercase a 64-hex SHA-256 digest (optional sha256: prefix)."""
    if not isinstance(raw, str):
        return None, f"{label}: sha256 must be string"
    digest = raw.strip().lower()
    if digest.startswith("sha256:"):
        digest = digest[7:]
    if not SHA256_HEX_RE.match(digest):
        return None, f"{label}: invalid 64-hex sha256 {raw!r}"
    return digest, None


def is_passing_validator_tag(value: Any) -> bool:
    """Return True iff external_validator string is non-empty and has no FAIL."""
    if not isinstance(value, str) or not value.strip():
        return False
    return FAIL_TOKEN_RE.search(value) is None


def canonical_sha256_hex(payload: Any) -> str:
    """Compute a deterministic SHA-256 hex digest over canonical JSON."""
    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

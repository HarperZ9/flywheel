# SPDX-License-Identifier: MIT
"""Strict numeric, SHA-256, license, and artifact guards for dataset_attest.

Provides fail-closed scalar and manifest validation helpers for BuildDB Parquet
and JFC3P RLVR dataset packs in pure Python stdlib.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

HONEST_SCOPE_LIMIT = (
    "Validates strict integer and finite float bounds, SHA-256 hex digests, "
    "exact MIT license strings, and manifest artifact hashes in pure Python "
    "stdlib. Does not parse binary Parquet column pages."
)

SHA256_HEX_RE = re.compile(r"^[0-9a-fA-F]{64}$")


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
        return None, f"{label}: sha256 must be a string"
    digest = raw.strip().lower()
    if digest.startswith("sha256:"):
        digest = digest[7:]
    if not SHA256_HEX_RE.match(digest):
        return None, f"{label}: invalid 64-hex sha256 {raw!r}"
    return digest, None


def is_mit_license(value: Any) -> bool:
    """Return True iff license is strictly the OSI MIT identifier."""
    return isinstance(value, str) and value.strip() == "MIT"


def validate_pass_rate(value: Any, label: str) -> list[str]:
    """Validate that a pass-rate metric or floor is finite and in [0.0, 1.0]."""
    if not is_strict_finite_float(value):
        return [f"{label}: non-finite or invalid pass rate {value!r}"]
    num = float(value)
    if num < 0.0 or num > 1.0:
        return [f"{label}: pass rate {num} outside [0.0, 1.0]"]
    return []


def verify_manifest_artifacts(
    manifest: Any,
    label: str,
    actual_hashes: dict[str, tuple[int, str]] | None = None,
) -> tuple[dict[str, str], list[str]]:
    """Validate artifact byte sizes and SHA-256 pins in a dataset manifest."""
    if not isinstance(manifest, dict):
        return {}, [f"{label}: manifest must be a JSON object"]
    arts = manifest.get("artifacts")
    if not isinstance(arts, dict) or not arts:
        return {}, [f"{label}: missing non-empty 'artifacts' mapping"]
    digests: dict[str, str] = {}
    errors: list[str] = []
    for name, meta in sorted(arts.items()):
        if not isinstance(meta, dict):
            errors.append(f"{label}.artifacts[{name}]: must be an object")
            continue
        sz = meta.get("bytes")
        if not is_strict_int(sz) or sz <= 0:
            errors.append(f"{label}.artifacts[{name}].bytes: invalid {sz!r}")
        sha, sha_err = normalize_sha256(meta.get("sha256"), f"{label}.{name}")
        if sha_err or sha is None:
            errors.append(sha_err or f"{label}.{name}: invalid sha256")
            continue
        digests[name] = sha
        if actual_hashes is not None and name in actual_hashes:
            act_sz, act_sha_raw = actual_hashes[name]
            act_sha, act_err = normalize_sha256(act_sha_raw, f"actual.{name}")
            if act_err or act_sz != sz or act_sha != sha:
                errors.append(f"{label}.artifacts[{name}]: digest or size mismatch")
    return digests, errors


def canonical_sha256_hex(payload: Any) -> str:
    """Compute a deterministic SHA-256 hex digest over canonical JSON."""
    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

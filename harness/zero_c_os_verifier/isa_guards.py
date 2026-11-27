# SPDX-License-Identifier: MIT
"""Strict ISA, SHA-256, binary-magic, and numeric guards for Zero-C BuildOS.

Provides fail-closed validation helpers for the 5-ISA Zero-C BuildOS verifier
covering x64-pe, x64-elf, rv64-elf, aarch64-elf, and wasm binaries.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

HONEST_SCOPE_LIMIT = (
    "Validates 5-ISA names, 64-hex SHA-256 digests, ELF/PE/WASM header magic "
    "bytes, and strict non-bool integer bounds in pure Python stdlib. Does "
    "not execute emulated CPU instructions."
)

REQUIRED_ISAS: frozenset[str] = frozenset(
    {"aarch64-elf", "rv64-elf", "wasm", "x64-elf", "x64-pe"}
)

REQUIRED_SLICE_COLUMNS: tuple[str, ...] = (
    "slice_id",
    "catalogue_id",
    "receipt_path",
    "isa",
    "zero_c",
    "runs_verified",
    "attacks_caught",
    "bin_path",
    "bin_bytes",
    "bin_sha256",
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


def parse_strict_positive_int(raw: Any, label: str) -> tuple[int | None, str | None]:
    """Parse a positive strict integer from int or ASCII digits."""
    if is_strict_int(raw):
        return (raw, None) if raw > 0 else (None, f"{label}: must be > 0")
    if isinstance(raw, str) and raw.strip().isdigit():
        val = int(raw.strip())
        return (val, None) if val > 0 else (None, f"{label}: must be > 0")
    return None, f"{label}: invalid positive int {raw!r}"


def parse_strict_nonneg_int(raw: Any, label: str) -> tuple[int | None, str | None]:
    """Parse a non-negative strict integer from int or ASCII digits."""
    if is_strict_int(raw):
        return (raw, None) if raw >= 0 else (None, f"{label}: must be >= 0")
    if isinstance(raw, str) and raw.strip().isdigit():
        return int(raw.strip()), None
    return None, f"{label}: invalid non-negative int {raw!r}"


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


def validate_binary_magic(isa: str, header: bytes) -> bool:
    """Check binary header magic bytes for each of the 5 BuildOS target ISAs."""
    if not isinstance(header, (bytes, bytearray)) or len(header) < 4:
        return False
    if isa == "x64-pe":
        return header[:2] == b"MZ"
    if isa in ("x64-elf", "rv64-elf", "aarch64-elf"):
        return header[:4] == b"\x7fELF"
    if isa == "wasm":
        return header[:4] == b"\x00asm"
    return False


def canonical_sha256_hex(payload: Any) -> str:
    """Compute a deterministic SHA-256 hex digest over canonical JSON."""
    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

# SPDX-License-Identifier: MIT
"""Strict hex-digest, capability-mask, and scalar guards for enclave_quote_gate.

Provides pure-stdlib fail-closed primitives for Zero-C BuildOS Confidential
Enclave verification (Slice 28): measurement digests, Poly1305 AEAD tags,
Ed25519 quote points, zero-egress capability masks, and binary magic bytes.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

HONEST_SCOPE_LIMIT = (
    "Validates 64-hex SHA-256/Ed25519 digests, 32-hex Poly1305 tags, strict "
    "integer capability bitmasks, finite float bounds, and ELF/PE/WASM magic "
    "bytes in pure Python stdlib. Does not execute elliptic-curve arithmetic."
)

REQUIRED_ENCLAVE_ISAS: frozenset[str] = frozenset(
    {"x64-pe", "x64-elf", "rv64-elf", "aarch64-elf", "wasm"}
)

CAP_NET_EGRESS_BIT: int = 2
DEFAULT_POLICY_ALLOW_MASK: int = 5

HEX64_RE = re.compile(r"^[0-9a-fA-F]{64}$")
HEX32_RE = re.compile(r"^[0-9a-fA-F]{32}$")


def is_strict_int(value: Any) -> bool:
    """Return True iff value is an int and not a bool."""
    return isinstance(value, int) and not isinstance(value, bool)


def is_strict_finite_float(value: Any) -> bool:
    """Return True iff value is a finite real int/float and not a bool."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


def normalize_hex(raw: Any, expected_len: int, label: str) -> tuple[str | None, str | None]:
    """Validate and lowercase a fixed-length hex digest (optional sha256: prefix)."""
    if not isinstance(raw, str):
        return None, f"{label}: hex digest must be string"
    val = raw.strip().lower()
    if val.startswith("sha256:"):
        val = val[7:]
    pat = HEX64_RE if expected_len == 64 else HEX32_RE
    if len(val) != expected_len or not pat.match(val):
        return None, f"{label}: invalid {expected_len}-hex string {raw!r}"
    return val, None


def check_zero_egress_caps(
    granted_caps: Any,
    *,
    policy_allow_mask: int = DEFAULT_POLICY_ALLOW_MASK,
    forbidden_egress_mask: int = CAP_NET_EGRESS_BIT,
) -> list[str]:
    """Verify granted_caps obeys zero-egress allowlist fail-closed."""
    if not is_strict_int(granted_caps) or granted_caps < 0:
        return [f"granted_caps: invalid mask {granted_caps!r}"]
    if not is_strict_int(policy_allow_mask) or policy_allow_mask < 0:
        return [f"policy_allow_mask: invalid mask {policy_allow_mask!r}"]
    if not is_strict_int(forbidden_egress_mask) or forbidden_egress_mask <= 0:
        return [f"forbidden_egress_mask: invalid mask {forbidden_egress_mask!r}"]
    errors: list[str] = []
    if (granted_caps & forbidden_egress_mask) != 0:
        errors.append(f"zero_egress_violation: forbidden bit set in {granted_caps}")
    if (granted_caps & ~policy_allow_mask) != 0:
        errors.append(f"policy_violation: caps {granted_caps} exceeds allow {policy_allow_mask}")
    return errors


def infer_isa_from_path(rel_path: str) -> str | None:
    """Infer one of the 5 BuildOS target ISAs from an artifact rel_path."""
    low = rel_path.strip().lower()
    if low.endswith(".aarch64.elf"):
        return "aarch64-elf"
    if low.endswith(".rv64.elf"):
        return "rv64-elf"
    if low.endswith(".x64.elf"):
        return "x64-elf"
    if low.endswith(".exe"):
        return "x64-pe"
    if low.endswith(".wasm"):
        return "wasm"
    return None


def validate_binary_magic(isa: str, header: bytes) -> bool:
    """Validate PE, ELF, or WASM binary header magic bytes."""
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

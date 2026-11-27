# SPDX-License-Identifier: MIT
"""Fail-closed FIPS 203 ML-KEM-512 parameter, coefficient, digest, and FO guards."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Sequence

MLKEM_Q: int = 3329
MLKEM_N: int = 256
MLKEM_K: int = 2

REQUIRED_ISAS: tuple[str, ...] = (
    "x64-pe",
    "x64-elf",
    "rv64-elf",
    "aarch64-elf",
    "wasm",
)

REQUIRED_FO_CONTROLS: tuple[str, ...] = (
    "mlkem_ct_tamper",
    "x25519_mitm",
    "non_canonical_coeff",
    "aead_tag_tamper",
)

_HEX_CHARS = frozenset("0123456789abcdef")


def is_strict_int(value: Any) -> bool:
    """Return True only for plain integers, rejecting booleans and floats."""
    return isinstance(value, int) and not isinstance(value, bool)


def normalize_sha256(digest: Any) -> str:
    """Strip an optional sha256: prefix and return lowercased hex if valid."""
    if not isinstance(digest, str):
        return ""
    raw = digest[7:] if digest.startswith("sha256:") else digest
    if len(raw) != 64:
        return ""
    low = raw.lower()
    if any(ch not in _HEX_CHARS for ch in low):
        return ""
    return low


def is_sha256_hex(digest: Any) -> bool:
    """Return True when digest is a valid 64-char hex SHA-256 string."""
    return bool(normalize_sha256(digest))


def sha256_file(path: Path) -> str:
    """Compute SHA-256 hex digest of a file using fixed-size chunks."""
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def check_fips203_params(q: Any, n: Any, k: Any) -> list[str]:
    """Validate FIPS 203 ML-KEM-512 ring parameters (q=3329, n=256, k=2)."""
    errs: list[str] = []
    if not is_strict_int(q) or q != MLKEM_Q:
        errs.append(f"invalid_mlkem_q:{q!r}")
    if not is_strict_int(n) or n != MLKEM_N:
        errs.append(f"invalid_mlkem_n:{n!r}")
    if not is_strict_int(k) or k != MLKEM_K:
        errs.append(f"invalid_mlkem_k:{k!r}")
    return errs


def check_canonical_coeffs(coeffs: Any) -> tuple[int, list[str]]:
    """Verify every polynomial coefficient is a strict int in [0, 3328]."""
    if not isinstance(coeffs, Sequence) or isinstance(coeffs, (str, bytes)):
        return 0, ["coefficients_not_sequence"]
    if len(coeffs) == 0:
        return 0, ["coefficients_empty"]
    errs: list[str] = []
    for idx, coeff in enumerate(coeffs):
        if not is_strict_int(coeff):
            errs.append(f"coeff_non_int_at_{idx}:{type(coeff).__name__}")
        elif coeff < 0 or coeff >= MLKEM_Q:
            errs.append(f"coeff_out_of_range_at_{idx}:{coeff}")
        if len(errs) >= 8:
            break
    return len(coeffs), errs


def check_fo_controls(
    controls: Sequence[Any],
    min_isas_per_control: int = 5,
) -> tuple[int, list[str]]:
    """Verify all required FO/PQ/hybrid attack controls fail closed across ISAs."""
    errs: list[str] = []
    seen: set[str] = set()
    passed = 0
    for ctrl in controls:
        name = getattr(ctrl, "name", "")
        if not isinstance(name, str) or not name:
            errs.append("fo_control_missing_name")
            continue
        if name in seen:
            errs.append(f"fo_control_duplicate:{name}")
            continue
        seen.add(name)
        if getattr(ctrl, "rejected", None) is not True:
            errs.append(f"fo_control_not_rejected:{name}")
            continue
        committed = getattr(ctrl, "hybrid_committed", None)
        if not is_strict_int(committed) or committed != 0:
            errs.append(f"fo_control_hybrid_committed:{name}:{committed!r}")
            continue
        code = getattr(ctrl, "error_code", None)
        if not is_strict_int(code) or code >= 0:
            errs.append(f"fo_control_non_negative_code:{name}:{code!r}")
            continue
        isas = getattr(ctrl, "isas_rejected", None)
        if not is_strict_int(isas) or isas < min_isas_per_control:
            errs.append(f"fo_control_isa_count:{name}:{isas!r}")
            continue
        passed += 1
    for req in REQUIRED_FO_CONTROLS:
        if req not in seen:
            errs.append(f"fo_control_missing:{req}")
    return passed, errs

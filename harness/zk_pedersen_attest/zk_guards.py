# SPDX-License-Identifier: MIT
"""Fail-closed Pedersen conservation, Edwards25519 cluster, and attack guards."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Sequence

CLUSTER_PILLARS: int = 4
CLUSTER_CURVE_EQS: int = 7

REQUIRED_ISAS: tuple[str, ...] = (
    "x64-pe",
    "x64-elf",
    "rv64-elf",
    "aarch64-elf",
    "wasm",
)

REQUIRED_ZK_ATTACKS: tuple[str, ...] = (
    "forged_schnorr_scalar",
    "value_inflation_breach",
    "blinding_mismatch",
    "forged_merkle_sibling",
)

REQUIRED_CLUSTER_ATTACKS: tuple[str, ...] = (
    "quic_replay",
    "vm_oob_write",
    "zk_inflation",
    "bft_equivocation",
    "bft_forged_sig",
    "cluster_root_tamper",
)

_HEX_CHARS = frozenset("0123456789abcdef")


def is_strict_int(value: Any) -> bool:
    """Return True only for plain integers, excluding booleans."""
    return isinstance(value, int) and not isinstance(value, bool)


def normalize_sha256(digest: Any) -> str:
    """Strip optional sha256: prefix and validate 64 lowercase hex characters."""
    if not isinstance(digest, str):
        return ""
    raw = digest[7:] if digest.startswith("sha256:") else digest
    if len(raw) != 64:
        return ""
    low = raw.lower()
    return low if all(ch in _HEX_CHARS for ch in low) else ""


def is_sha256_hex(digest: Any) -> bool:
    """Return True when digest is a valid 64-char hex SHA-256 string."""
    return bool(normalize_sha256(digest))


def sha256_file(path: Path) -> str:
    """Compute streaming SHA-256 hex digest for an artifact file."""
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def rfc6962_mth(leaves: Sequence[bytes]) -> bytes:
    """Compute RFC 6962 Merkle Tree Hash MTH(D[0:n]) over ordered leaf byte strings."""
    n = len(leaves)
    if n == 0:
        return hashlib.sha256(b"").digest()
    if n == 1:
        return hashlib.sha256(b"\x00" + leaves[0]).digest()
    k = 1 << ((n - 1).bit_length() - 1)
    return hashlib.sha256(b"\x01" + rfc6962_mth(leaves[:k]) + rfc6962_mth(leaves[k:])).digest()


def check_pedersen_conservation(
    v_in: Any,
    v_out1: Any,
    v_out2: Any,
    verified: Any,
) -> list[str]:
    """Verify non-negative Pedersen conservation v_in == v_out1 + v_out2 and verified == 1."""
    errs: list[str] = []
    for label, val in (("v_in", v_in), ("v_out1", v_out1), ("v_out2", v_out2)):
        if not is_strict_int(val) or val < 0:
            errs.append(f"invalid_pedersen_{label}:{val!r}")
    if not errs and v_in != (v_out1 + v_out2):
        errs.append(f"value_inflation_breach:{v_in}!={v_out1}+{v_out2}")
    if not is_strict_int(verified) or verified != 1:
        errs.append(f"zk_proof_not_verified:{verified!r}")
    return errs


def check_cluster_pillars(
    pillars: Any,
    curve_eqs: Any,
    pillar_roots: Sequence[str],
    cluster_root_hex: str,
    verify_mth: bool = False,
) -> list[str]:
    """Verify Slice 35 BuildOS-2.1 4-pillar Edwards25519 cluster invariants."""
    errs: list[str] = []
    if not is_strict_int(pillars) or pillars != CLUSTER_PILLARS:
        errs.append(f"invalid_cluster_pillars:{pillars!r}")
    if not is_strict_int(curve_eqs) or curve_eqs < CLUSTER_CURVE_EQS:
        errs.append(f"invalid_curve_eqs:{curve_eqs!r}")
    norm_root = normalize_sha256(cluster_root_hex)
    if not norm_root:
        errs.append("invalid_cluster_root_hex")
    norm_leaves: list[bytes] = []
    for idx, hx in enumerate(pillar_roots):
        norm = normalize_sha256(hx)
        if not norm:
            errs.append(f"invalid_pillar_root_{idx}")
        else:
            norm_leaves.append(bytes.fromhex(norm))
    if len(pillar_roots) != CLUSTER_PILLARS:
        errs.append(f"pillar_root_count_mismatch:{len(pillar_roots)}")
    if verify_mth and not errs and rfc6962_mth(norm_leaves).hex() != norm_root:
        errs.append("cluster_rfc6962_mth_mismatch")
    return errs


def check_attack_controls(
    attacks: Sequence[Any],
    required_names: Sequence[str],
    min_isas: int = 5,
) -> tuple[int, int, list[str]]:
    """Verify required ZK or cluster attacks fail closed across all 5 ISAs."""
    errs: list[str] = []
    allowed = set(required_names)
    seen: set[str] = set()
    passed, total_rejs = 0, 0
    for atk in attacks:
        name = getattr(atk, "name", "")
        if not isinstance(name, str) or name not in allowed:
            errs.append(f"unknown_attack:{name!r}")
            continue
        if name in seen:
            errs.append(f"duplicate_attack:{name}")
            continue
        seen.add(name)
        if getattr(atk, "rejected", None) is not True:
            errs.append(f"attack_not_rejected:{name}")
            continue
        committed = getattr(atk, "committed", None)
        if not is_strict_int(committed) or committed != 0:
            errs.append(f"attack_committed_nonzero:{name}:{committed!r}")
            continue
        code = getattr(atk, "error_code", None)
        if not is_strict_int(code) or code >= 0:
            errs.append(f"attack_non_negative_code:{name}:{code!r}")
            continue
        isas = getattr(atk, "isas_rejected", None)
        if not is_strict_int(isas) or isas < min_isas:
            errs.append(f"attack_isa_count_low:{name}:{isas!r}")
            continue
        passed += 1
        total_rejs += isas
    for req in required_names:
        if req not in seen:
            errs.append(f"missing_attack:{req}")
    return passed, total_rejs, errs

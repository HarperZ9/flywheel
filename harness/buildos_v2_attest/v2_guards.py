# SPDX-License-Identifier: MIT
"""Fail-closed RFC 6962 Merkle tree, 12-subsystem, and 8-attack guards for BuildOS-2.0."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Sequence

SOVEREIGN_MERKLE_ROOT_HEX: str = (
    "b0169274ea5bb300813d8d409c1098cbd92cb7490dcaf3fe30865b15eddc393f"
)

REQUIRED_ISAS: tuple[str, ...] = (
    "x64-pe",
    "x64-elf",
    "rv64-elf",
    "aarch64-elf",
    "wasm",
)

REQUIRED_SUBSYSTEMS: tuple[str, ...] = (
    "signed_boot",
    "smp_mmu",
    "iommu_nvme",
    "pq_hybrid_kem",
    "enclave_seal",
    "enclave_quote",
    "gpu_queue",
    "gpu_vram",
    "compositor",
    "hid_guard",
    "q15_audio",
    "merkle_commit",
)

REQUIRED_ATTACKS: tuple[str, ...] = (
    "bad_boot_sig",
    "sv39_wx_violation",
    "iommu_dma_escape",
    "mlkem_ct_tamper",
    "enclave_meas_mismatch",
    "uncertified_gpu_shader",
    "compositor_xwin_read",
    "hid_keylogger_tap",
)

_HEX_CHARS = frozenset("0123456789abcdef")


def is_strict_int(value: Any) -> bool:
    """Return True only for plain integers, excluding booleans."""
    return isinstance(value, int) and not isinstance(value, bool)


def normalize_sha256(digest: Any) -> str:
    """Strip an optional sha256: prefix and validate 64 lowercase hex characters."""
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
    """Compute streaming SHA-256 hex digest for an artifact file."""
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def rfc6962_leaf_hash(leaf_data: bytes) -> bytes:
    """Compute RFC 6962 leaf hash SHA256(0x00 || leaf_data)."""
    return hashlib.sha256(b"\x00" + leaf_data).digest()


def rfc6962_node_hash(left: bytes, right: bytes) -> bytes:
    """Compute RFC 6962 interior node hash SHA256(0x01 || left || right)."""
    return hashlib.sha256(b"\x01" + left + right).digest()


def rfc6962_mth(leaves: Sequence[bytes]) -> bytes:
    """Compute RFC 6962 Merkle Tree Hash MTH(D[0:n]) over ordered leaf byte strings."""
    n = len(leaves)
    if n == 0:
        return hashlib.sha256(b"").digest()
    if n == 1:
        return rfc6962_leaf_hash(leaves[0])
    k = 1 << ((n - 1).bit_length() - 1)
    return rfc6962_node_hash(rfc6962_mth(leaves[:k]), rfc6962_mth(leaves[k:]))


def check_subsystem_leaves(
    subsystems: Sequence[Any],
    expected_root_hex: str,
    verify_mth: bool = True,
) -> tuple[int, list[str]]:
    """Verify all 12 BuildOS-2.0 subsystem leaves and optional RFC 6962 MTH root."""
    errs: list[str] = []
    seen: set[str] = set()
    ordered_bytes: list[bytes] = []
    for item in subsystems:
        name = getattr(item, "name", "")
        leaf_hex = normalize_sha256(getattr(item, "digest_hex", ""))
        if not isinstance(name, str) or name not in REQUIRED_SUBSYSTEMS:
            errs.append(f"unknown_subsystem:{name!r}")
            continue
        if name in seen:
            errs.append(f"duplicate_subsystem:{name}")
            continue
        if not leaf_hex:
            errs.append(f"invalid_subsystem_digest:{name}")
            continue
        seen.add(name)
        ordered_bytes.append(bytes.fromhex(leaf_hex))
    for req in REQUIRED_SUBSYSTEMS:
        if req not in seen:
            errs.append(f"missing_subsystem:{req}")
    if verify_mth and not errs and len(ordered_bytes) == 12:
        computed = rfc6962_mth(ordered_bytes).hex()
        norm_expected = normalize_sha256(expected_root_hex)
        if not norm_expected or computed != norm_expected:
            errs.append(f"rfc6962_mth_mismatch:{computed[:16]}!={norm_expected[:16]}")
    return len(seen), errs


def check_v2_attacks(
    attacks: Sequence[Any],
    min_isas: int = 5,
) -> tuple[int, int, list[str]]:
    """Verify all 8 cross-subsystem BuildOS-2.0 attacks fail closed across 5 ISAs."""
    errs: list[str] = []
    seen: set[str] = set()
    passed = 0
    total_rejections = 0
    for atk in attacks:
        name = getattr(atk, "name", "")
        if not isinstance(name, str) or name not in REQUIRED_ATTACKS:
            errs.append(f"unknown_attack:{name!r}")
            continue
        if name in seen:
            errs.append(f"duplicate_attack:{name}")
            continue
        seen.add(name)
        if getattr(atk, "rejected", None) is not True:
            errs.append(f"attack_not_rejected:{name}")
            continue
        committed = getattr(atk, "sovereign_committed", None)
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
        total_rejections += isas
    for req in REQUIRED_ATTACKS:
        if req not in seen:
            errs.append(f"missing_attack:{req}")
    return passed, total_rejections, errs

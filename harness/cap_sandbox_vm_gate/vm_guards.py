# SPDX-License-Identifier: MIT
"""Fail-closed fuel-metering, W^X linear-memory, and capability hostcall guards."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Sequence

VM_ROOT_HEX: str = (
    "a22ee7e6e2af59885b7a7de106f325ffb500136895cc3524bd0f5e668053575b"
)
DEFAULT_MAX_FUEL: int = 512
DEFAULT_MEM_WORDS: int = 32
CODE_SEG_BASE: int = 1024
CAP_CRYPTO: int = 1
CAP_LOG: int = 2

REQUIRED_ISAS: tuple[str, ...] = (
    "x64-pe",
    "x64-elf",
    "rv64-elf",
    "aarch64-elf",
    "wasm",
)

REQUIRED_VM_ATTACKS: tuple[str, ...] = (
    "fuel_exhaustion",
    "oob_linear_memory",
    "wx_code_write",
    "unauthorized_hostcall",
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


def check_vm_execution_trace(
    fuel_budget: Any,
    fuel_used: Any,
    cap_mask: Any,
    mem_writes: Sequence[Any],
    hostcalls: Sequence[Any],
    max_fuel: int = DEFAULT_MAX_FUEL,
    mem_words: int = DEFAULT_MEM_WORDS,
    code_base: int = CODE_SEG_BASE,
) -> list[str]:
    """Verify fuel bounds, linear memory W^X writes, and capability-gated hostcalls."""
    errs: list[str] = []
    if not is_strict_int(fuel_budget) or fuel_budget <= 0 or fuel_budget > max_fuel:
        errs.append(f"invalid_fuel_budget:{fuel_budget!r}")
    if not is_strict_int(fuel_used) or fuel_used < 0:
        errs.append(f"invalid_fuel_used:{fuel_used!r}")
    elif is_strict_int(fuel_budget) and fuel_used > fuel_budget:
        errs.append(f"fuel_budget_exceeded:{fuel_used}>{fuel_budget}")
    if not is_strict_int(cap_mask) or cap_mask < 0:
        errs.append(f"invalid_cap_mask:{cap_mask!r}")
    for idx, addr in enumerate(mem_writes):
        if not is_strict_int(addr):
            errs.append(f"mem_write_non_int_{idx}")
        elif addr >= code_base:
            errs.append(f"wx_code_write_violation_{idx}:{addr}")
        elif addr < 0 or addr >= mem_words:
            errs.append(f"oob_linear_memory_write_{idx}:{addr}")
    mask_i = cap_mask if is_strict_int(cap_mask) and cap_mask >= 0 else 0
    for idx, hc in enumerate(hostcalls):
        cap_bit = getattr(hc, "required_cap", None)
        allowed = getattr(hc, "allowed", None)
        if not is_strict_int(cap_bit) or cap_bit <= 0 or not isinstance(allowed, bool):
            errs.append(f"invalid_hostcall_record_{idx}")
            continue
        has_cap = (mask_i & cap_bit) == cap_bit
        if allowed and not has_cap:
            errs.append(f"unauthorized_hostcall_allowed_{idx}:cap={cap_bit}")
        elif not allowed and has_cap:
            errs.append(f"authorized_hostcall_unexpected_deny_{idx}:cap={cap_bit}")
    return errs


def check_vm_attacks(
    attacks: Sequence[Any],
    min_isas: int = 5,
) -> tuple[int, int, list[str]]:
    """Verify all 4 sandbox-escape attack vectors fail closed across 5 ISAs (20/20)."""
    errs: list[str] = []
    seen: set[str] = set()
    passed, total_rejs = 0, 0
    for atk in attacks:
        name = getattr(atk, "name", "")
        if not isinstance(name, str) or name not in REQUIRED_VM_ATTACKS:
            errs.append(f"unknown_vm_attack:{name!r}")
            continue
        if name in seen:
            errs.append(f"duplicate_vm_attack:{name}")
            continue
        seen.add(name)
        if getattr(atk, "rejected", None) is not True:
            errs.append(f"vm_attack_not_rejected:{name}")
            continue
        committed = getattr(atk, "committed", None)
        if not is_strict_int(committed) or committed != 0:
            errs.append(f"vm_attack_committed_nonzero:{name}:{committed!r}")
            continue
        code = getattr(atk, "error_code", None)
        if not is_strict_int(code) or code >= 0:
            errs.append(f"vm_attack_non_negative_code:{name}:{code!r}")
            continue
        isas = getattr(atk, "isas_rejected", None)
        if not is_strict_int(isas) or isas < min_isas:
            errs.append(f"vm_attack_isa_count_low:{name}:{isas!r}")
            continue
        passed += 1
        total_rejs += isas
    for req in REQUIRED_VM_ATTACKS:
        if req not in seen:
            errs.append(f"missing_vm_attack:{req}")
    return passed, total_rejs, errs

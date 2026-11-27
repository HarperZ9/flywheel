# SPDX-License-Identifier: MIT
"""Fail-closed Flywheel oracle for Zero-C 5-ISA BuildOS slices (Slices 17..24).

Verifies that every Zero-C BuildOS slice covers all 5 target ISAs (x64-pe,
x64-elf, rv64-elf, aarch64-elf, wasm), enforces zero_c == 1, meets attack
rejection and run floors, cross-checks catalogue provenance and optional
on-disk binary digests, and seals zero_c_os_attestation_sha256.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .isa_guards import (
    REQUIRED_ISAS,
    canonical_sha256_hex,
    is_strict_int,
    normalize_sha256,
)
from .slice_parser import ZeroCSliceBinary, parse_slices_index_tsv

HONEST_SCOPE_LIMIT = (
    "Verifies 5-ISA completeness, zero-C flag, attack rejection counts, "
    "catalogue provenance, and binary SHA-256 digests across BuildOS slices "
    "in pure Python stdlib. Does not emulate RV64/AArch64 or execute kernels."
)


@dataclass(frozen=True)
class ZeroCOSReport:
    """Fail-closed attestation verdict for Zero-C 5-ISA BuildOS slices."""

    passed: bool
    slice_count: int
    binary_count: int
    isa_complete_slices: int
    total_attacks_caught: int
    slice_ids: tuple[str, ...]
    zero_c_os_attestation_sha256: str
    violations: tuple[str, ...]
    honest_scope_limit: str = HONEST_SCOPE_LIMIT


def _validate_thresholds(
    min_slices: int,
    min_attacks: int,
    min_runs: int,
    known_cids: set[int] | None,
) -> list[str]:
    errors: list[str] = []
    for name, val in (
        ("min_slices", min_slices),
        ("min_attacks_per_slice", min_attacks),
        ("min_runs_per_slice", min_runs),
    ):
        if not is_strict_int(val) or val <= 0:
            errors.append(f"{name}: expected positive strict int, got {val!r}")
    if known_cids is not None:
        for cid in known_cids:
            if not is_strict_int(cid) or cid <= 0:
                errors.append(f"known_catalogue_ids: invalid ID {cid!r}")
                break
    return errors


def _check_grouped_slices(
    grouped: dict[str, list[ZeroCSliceBinary]],
    min_slices: int,
    min_attacks: int,
    min_runs: int,
    known_cids: set[int] | None,
    binary_hashes: dict[tuple[str, str], tuple[int, str]] | None,
    receipt_verdicts: dict[int, bool] | None,
) -> tuple[int, int, list[str]]:
    errors: list[str] = []
    if len(grouped) < min_slices:
        errors.append(f"slice_count: got {len(grouped)} < min_slices {min_slices}")
    complete_slices = 0
    total_attacks = 0
    for sid, items in sorted(grouped.items()):
        isas = [b.isa for b in items]
        if len(isas) != len(set(isas)):
            errors.append(f"{sid}: duplicate ISA entries detected")
        missing = sorted(REQUIRED_ISAS - set(isas))
        if missing:
            errors.append(f"{sid}: missing required ISAs {missing}")
        else:
            complete_slices += 1
        cids = {b.catalogue_id for b in items}
        if len(cids) != 1:
            errors.append(f"{sid}: inconsistent catalogue IDs {sorted(cids)}")
        slice_attacks = min(b.attacks_caught for b in items)
        total_attacks += slice_attacks
        errors.extend(
            _check_slice_items(
                sid, items, min_attacks, min_runs, known_cids, binary_hashes, receipt_verdicts
            )
        )
    return complete_slices, total_attacks, errors


def _check_slice_items(
    sid: str,
    items: list[ZeroCSliceBinary],
    min_attacks: int,
    min_runs: int,
    known_cids: set[int] | None,
    binary_hashes: dict[tuple[str, str], tuple[int, str]] | None,
    receipt_verdicts: dict[int, bool] | None,
) -> list[str]:
    errors: list[str] = []
    for b in items:
        if b.zero_c != 1:
            errors.append(f"{sid}/{b.isa}: zero_c flag must be 1, got {b.zero_c}")
        if b.attacks_caught < min_attacks:
            errors.append(f"{sid}/{b.isa}: attacks_caught {b.attacks_caught} < {min_attacks}")
        if b.runs_verified < min_runs:
            errors.append(f"{sid}/{b.isa}: runs_verified {b.runs_verified} < {min_runs}")
        if known_cids is not None and b.catalogue_id not in known_cids:
            errors.append(f"{sid}/{b.isa}: forged or absent catalogue_id {b.catalogue_id}")
        if receipt_verdicts is not None and receipt_verdicts.get(b.catalogue_id) is not True:
            errors.append(f"{sid}/{b.isa}: receipt {b.catalogue_id} not MATCH")
        if binary_hashes is not None:
            actual = binary_hashes.get((sid, b.isa))
            if actual is None:
                errors.append(f"{sid}/{b.isa}: missing on-disk binary hash")
            else:
                act_bytes, act_sha_raw = actual
                act_sha, sha_err = normalize_sha256(act_sha_raw, f"{sid}/{b.isa}")
                if sha_err or act_bytes != b.bin_bytes or act_sha != b.bin_sha256:
                    errors.append(f"{sid}/{b.isa}: binary digest or size mismatch")
    return errors


def verify_zero_c_os(
    records: list[ZeroCSliceBinary],
    *,
    min_slices: int = 7,
    min_attacks_per_slice: int = 4,
    min_runs_per_slice: int = 25,
    known_catalogue_ids: set[int] | None = None,
    binary_hashes: dict[tuple[str, str], tuple[int, str]] | None = None,
    receipt_verdicts: dict[int, bool] | None = None,
) -> ZeroCOSReport:
    """Run fail-closed verification across Zero-C 5-ISA BuildOS slice records."""
    if not isinstance(records, list):
        return _fail_report("records: expected list of ZeroCSliceBinary")
    pre_errs = _validate_thresholds(
        min_slices, min_attacks_per_slice, min_runs_per_slice, known_catalogue_ids
    )
    if pre_errs:
        return _fail_report("; ".join(pre_errs))
    grouped: dict[str, list[ZeroCSliceBinary]] = {}
    for rec in records:
        if not isinstance(rec, ZeroCSliceBinary):
            return _fail_report("records: invalid element type")
        grouped.setdefault(rec.slice_id, []).append(rec)
    complete, attacks, violations = _check_grouped_slices(
        grouped,
        min_slices,
        min_attacks_per_slice,
        min_runs_per_slice,
        known_catalogue_ids,
        binary_hashes,
        receipt_verdicts,
    )
    return _build_os_report(records, grouped, complete, attacks, violations)


def _build_os_report(
    records: list[ZeroCSliceBinary],
    grouped: dict[str, list[ZeroCSliceBinary]],
    complete: int,
    attacks: int,
    violations: list[str],
) -> ZeroCOSReport:
    ordered = sorted(records, key=lambda r: (r.slice_id, r.isa))
    attest = {
        "slice_ids": sorted(grouped),
        "binary_count": len(ordered),
        "binaries": [
            (r.slice_id, r.catalogue_id, r.isa, r.zero_c, r.runs_verified, r.attacks_caught, r.bin_bytes, r.bin_sha256)
            for r in ordered
        ],
    }
    return ZeroCOSReport(
        passed=len(violations) == 0,
        slice_count=len(grouped),
        binary_count=len(ordered),
        isa_complete_slices=complete,
        total_attacks_caught=attacks,
        slice_ids=tuple(sorted(grouped)),
        zero_c_os_attestation_sha256=canonical_sha256_hex(attest),
        violations=tuple(violations),
    )


def _fail_report(message: str) -> ZeroCOSReport:
    return ZeroCOSReport(False, 0, 0, 0, 0, (), "", (message,))


def verify_zero_c_os_tsv(
    tsv_bytes: bytes,
    *,
    extra_records: list[ZeroCSliceBinary] | None = None,
    min_slices: int = 7,
    min_attacks_per_slice: int = 4,
    min_runs_per_slice: int = 25,
    known_catalogue_ids: set[int] | None = None,
    binary_hashes: dict[tuple[str, str], tuple[int, str]] | None = None,
    receipt_verdicts: dict[int, bool] | None = None,
) -> ZeroCOSReport:
    """Parse buildos_zeroc_slices_index.tsv bytes and verify fail-closed."""
    if not isinstance(tsv_bytes, (bytes, bytearray)):
        return _fail_report("tsv_bytes: expected bytes")
    try:
        tsv_text = bytes(tsv_bytes).decode("utf-8")
    except UnicodeDecodeError:
        return _fail_report("tsv_bytes: invalid UTF-8")
    parsed, parse_errs = parse_slices_index_tsv(tsv_text)
    if parse_errs:
        return _fail_report("; ".join(parse_errs))
    combined = parsed + (list(extra_records) if extra_records else [])
    return verify_zero_c_os(
        combined,
        min_slices=min_slices,
        min_attacks_per_slice=min_attacks_per_slice,
        min_runs_per_slice=min_runs_per_slice,
        known_catalogue_ids=known_catalogue_ids,
        binary_hashes=binary_hashes,
        receipt_verdicts=receipt_verdicts,
    )


def hash_binary_file(path: Path | str) -> tuple[int, str]:
    """Return (byte_size, sha256_hex) for an on-disk BuildOS binary."""
    data = Path(path).read_bytes()
    return len(data), hashlib.sha256(data).hexdigest()

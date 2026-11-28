# SPDX-License-Identifier: MIT
"""Fail-closed oracle and CLI for Zero-C Threshold HSM + Erasure RAID-6 FS."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from harness.threshold_storage_attest.storage_guards import (
    REQUIRED_ISAS,
    StorageAttestError,
    load_json_object,
    verify_isa_binary_on_disk,
)
from harness.threshold_storage_attest.storage_parser import (
    SliceReceiptSummary,
    ThresholdStorageBundle,
    parse_slice_receipt,
)

HSM_EXCERPT_SCHEMA = "wave153a-slice36-zeroc-threshold-hsm/1"
RAID_EXCERPT_SCHEMA = "wave161b-slice37-zeroc-erasure-raid-fs/1"
REQUIRED_ATTACKS_PER_SLICE = 20


@dataclass(frozen=True)
class ThresholdStorageVerdict:
    passed: bool
    hsm_isa_count: int
    raid_isa_count: int
    disk_binaries_verified: int
    hsm_audit_root_hex: str
    raid_merkle_root_hex: str
    total_attacks_caught: int
    reasons: tuple[str, ...]


def _check_common_slice(
    rec: SliceReceiptSummary,
    expected_schema: str,
    disk_root: Path | None,
    reasons: list[str],
) -> int:
    if rec.verdict != "MATCH" or rec.exit_code != 0:
        reasons.append(f"{rec.label}: verdict != MATCH or oracle exit_code != 0")
    if rec.engine != "buildlang":
        reasons.append(f"{rec.label}: unexpected engine '{rec.engine}'")
    if not rec.excerpt_ok or rec.excerpt_schema != expected_schema:
        reasons.append(f"{rec.label}: excerpt schema or ok flag mismatch")
    if rec.source_bld_relpath is None:
        reasons.append(f"{rec.label}: missing BuildLang .bld source artifact")
    if rec.total_verified_zero_c_binaries < 25:
        reasons.append(f"{rec.label}: total_verified_zero_c_binaries < 25")
    seen_isas = [b.isa for b in rec.isa_binaries]
    if len(seen_isas) != len(set(seen_isas)):
        reasons.append(f"{rec.label}: duplicate ISA binary entries")
    if set(seen_isas) != REQUIRED_ISAS:
        reasons.append(f"{rec.label}: incomplete 5-ISA binary set")
    if rec.attacks_caught is not None and rec.attacks_total is not None:
        if (
            rec.attacks_caught < REQUIRED_ATTACKS_PER_SLICE
            or rec.attacks_caught != rec.attacks_total
        ):
            reasons.append(
                f"{rec.label}: attack matrix failed ({rec.attacks_caught}/{rec.attacks_total})"
            )
    disk_ok = 0
    if disk_root is not None:
        for b in rec.isa_binaries:
            err = verify_isa_binary_on_disk(
                disk_root, b.rel_path, b.isa, b.size_bytes, b.sha256
            )
            if err is not None:
                reasons.append(f"{rec.label}: {err}")
            else:
                disk_ok += 1
    return disk_ok


def verify_threshold_storage_bundle(
    bundle: ThresholdStorageBundle,
    *,
    hsm_root: Path | None = None,
    raid_root: Path | None = None,
) -> ThresholdStorageVerdict:
    """Verify both Slice 36 Threshold HSM and Slice 37 Erasure RAID-6 receipts."""
    reasons: list[str] = []
    disk_ok = _check_common_slice(bundle.hsm, HSM_EXCERPT_SCHEMA, hsm_root, reasons)
    disk_ok += _check_common_slice(bundle.raid, RAID_EXCERPT_SCHEMA, raid_root, reasons)
    if bundle.hsm.params.get("t") != 3 or bundle.hsm.params.get("n") != 5:
        reasons.append("hsm: threshold parameters must be (t=3, n=5)")
    if bundle.raid.params.get("k") != 4 or bundle.raid.params.get("m") != 2:
        reasons.append("raid: Reed-Solomon parameters must be (k=4, m=2)")
    if bundle.raid.params.get("healed_patterns", 0) < 15:
        reasons.append(
            "raid: healed_patterns must cover all 15 1- and 2-erasure patterns"
        )
    if bundle.hsm.merkle_root_hex == bundle.raid.merkle_root_hex:
        reasons.append("cross-slice: HSM and RAID-6 RFC 6962 roots must be distinct")
    hsm_atk = bundle.hsm.attacks_caught or 0
    raid_atk = bundle.raid.attacks_caught or 0
    return ThresholdStorageVerdict(
        passed=not reasons,
        hsm_isa_count=len(bundle.hsm.isa_binaries),
        raid_isa_count=len(bundle.raid.isa_binaries),
        disk_binaries_verified=disk_ok,
        hsm_audit_root_hex=bundle.hsm.merkle_root_hex,
        raid_merkle_root_hex=bundle.raid.merkle_root_hex,
        total_attacks_caught=hsm_atk + raid_atk,
        reasons=tuple(reasons),
    )


def verify_threshold_storage_files(
    hsm_receipt_path: Path,
    raid_receipt_path: Path,
    *,
    check_binaries_on_disk: bool = False,
    artifact_root: Path | None = None,
    hsm_attacks: dict[str, Any] | None = None,
    raid_attacks: dict[str, Any] | None = None,
) -> ThresholdStorageVerdict:
    """Load, parse, and verify Slice 36 HSM + Slice 37 RAID-6 receipts from disk."""
    try:
        hsm_raw = load_json_object(hsm_receipt_path, "hsm")
        raid_raw = load_json_object(raid_receipt_path, "raid")
        bundle = ThresholdStorageBundle(
            hsm=parse_slice_receipt(
                hsm_raw, slice_kind="hsm", attack_summary=hsm_attacks
            ),
            raid=parse_slice_receipt(
                raid_raw, slice_kind="raid", attack_summary=raid_attacks
            ),
        )
    except StorageAttestError as exc:
        return ThresholdStorageVerdict(
            passed=False,
            hsm_isa_count=0,
            raid_isa_count=0,
            disk_binaries_verified=0,
            hsm_audit_root_hex="",
            raid_merkle_root_hex="",
            total_attacks_caught=0,
            reasons=(str(exc),),
        )
    h_root = (
        (artifact_root or hsm_receipt_path.parent) if check_binaries_on_disk else None
    )
    r_root = (
        (artifact_root or raid_receipt_path.parent) if check_binaries_on_disk else None
    )
    return verify_threshold_storage_bundle(bundle, hsm_root=h_root, raid_root=r_root)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point returning 0 on PASS and 2 on fail-closed rejection."""
    parser = argparse.ArgumentParser(
        description="Verify Zero-C 5-ISA Threshold HSM and RS(4,2) Self-Healing RAID-6 receipts."
    )
    parser.add_argument("--hsm-receipt", type=Path, required=True)
    parser.add_argument("--raid-receipt", type=Path, required=True)
    parser.add_argument("--check-binaries-on-disk", action="store_true")
    parser.add_argument("--artifact-root", type=Path, default=None)
    args = parser.parse_args(argv)
    verdict = verify_threshold_storage_files(
        args.hsm_receipt,
        args.raid_receipt,
        check_binaries_on_disk=args.check_binaries_on_disk,
        artifact_root=args.artifact_root,
    )
    print(json.dumps(asdict(verdict), indent=2))
    return 0 if verdict.passed else 2


if __name__ == "__main__":
    sys.exit(main())

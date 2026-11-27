# SPDX-License-Identifier: MIT
"""Fail-closed attestation oracle for Unified 12-Subsystem Zero-C BuildOS-2.0."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import sys
from typing import Sequence

from harness.buildos_v2_attest.v2_guards import (
    REQUIRED_ISAS,
    SOVEREIGN_MERKLE_ROOT_HEX,
    check_subsystem_leaves,
    check_v2_attacks,
    is_sha256_hex,
    is_strict_int,
    normalize_sha256,
    sha256_file,
)
from harness.buildos_v2_attest.v2_parser import (
    BuildOSV2Bundle,
    parse_buildos_v2_payload,
    parse_buildos_v2_receipt,
)


@dataclass(frozen=True)
class BuildOSV2Policy:
    """Configurable verification policy for BuildOS-2.0 sovereign bundles."""

    require_all_5_isas: bool = True
    require_12_subsystems: bool = True
    require_8_attacks: bool = True
    verify_rfc6962_mth: bool = True
    expected_root_prefix: str = SOVEREIGN_MERKLE_ROOT_HEX[:16]
    check_on_disk: bool = False
    max_wasm_bytes: int = 163840


@dataclass(frozen=True)
class BuildOSV2Report:
    """Deterministic fail-closed verdict emitted by buildos_v2_attest."""

    ok: bool
    verdict: str
    merkle_root: str
    subsystems_verified: int
    isas_verified: tuple[str, ...]
    attacks_verified: int
    total_attack_rejections: int
    errors: tuple[str, ...]
    report_sha256: str


def _seal(
    ok: bool,
    root: str,
    subs: int,
    isas: list[str],
    atks: int,
    rejs: int,
    errs: list[str],
) -> BuildOSV2Report:
    verdict = "PASS" if ok else "REJECT"
    body = {
        "ok": ok,
        "verdict": verdict,
        "merkle_root": root,
        "subsystems_verified": subs,
        "isas_verified": sorted(isas),
        "attacks_verified": atks,
        "total_attack_rejections": rejs,
        "errors": list(errs),
    }
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return BuildOSV2Report(
        ok=ok,
        verdict=verdict,
        merkle_root=root,
        subsystems_verified=subs,
        isas_verified=tuple(sorted(isas)),
        attacks_verified=atks,
        total_attack_rejections=rejs,
        errors=tuple(errs),
        report_sha256=digest,
    )


def _check_binaries(
    bundle: BuildOSV2Bundle,
    pol: BuildOSV2Policy,
    artifact_root: Path | None,
    errs: list[str],
) -> list[str]:
    seen: set[str] = set()
    verified: list[str] = []
    for rec in bundle.binaries:
        if rec.isa not in REQUIRED_ISAS:
            errs.append(f"unknown_isa:{rec.isa}")
            continue
        if rec.isa in seen:
            errs.append(f"duplicate_isa:{rec.isa}")
            continue
        seen.add(rec.isa)
        if not is_strict_int(rec.byte_size) or rec.byte_size <= 0:
            errs.append(f"invalid_byte_size:{rec.isa}:{rec.byte_size}")
            continue
        if rec.isa == "wasm" and rec.byte_size > pol.max_wasm_bytes:
            errs.append(f"wasm_exceeds_budget:{rec.byte_size}>{pol.max_wasm_bytes}")
            continue
        if not is_sha256_hex(rec.sha256):
            errs.append(f"invalid_sha256:{rec.isa}")
            continue
        if pol.check_on_disk and artifact_root is not None:
            fp = artifact_root / rec.rel_path
            if not fp.is_file():
                errs.append(f"missing_on_disk:{rec.isa}")
                continue
            if sha256_file(fp) != rec.sha256:
                errs.append(f"sha256_mismatch:{rec.isa}")
                continue
        verified.append(rec.isa)
    if pol.require_all_5_isas:
        for req in REQUIRED_ISAS:
            if req not in seen:
                errs.append(f"missing_isa:{req}")
    return verified


def verify_buildos_v2_bundle(
    bundle: BuildOSV2Bundle,
    policy: BuildOSV2Policy | None = None,
    artifact_root: Path | None = None,
) -> BuildOSV2Report:
    """Verify a BuildOS-2.0 sovereign bundle fail-closed."""
    pol = policy or BuildOSV2Policy()
    errs: list[str] = list(bundle.parse_errors)
    if bundle.verdict not in ("MATCH", "PASS"):
        errs.append(f"invalid_verdict:{bundle.verdict}")
    if not is_strict_int(bundle.oracle_exit_code) or bundle.oracle_exit_code != 0:
        errs.append(f"nonzero_oracle_exit:{bundle.oracle_exit_code}")
    if not is_sha256_hex(bundle.claim_sha256):
        errs.append("invalid_claim_sha256")
    root_low = bundle.merkle_root.lower()
    if pol.expected_root_prefix and not root_low.startswith(pol.expected_root_prefix.lower()):
        errs.append(f"merkle_root_prefix_mismatch:{root_low[:16]}")
    if pol.verify_rfc6962_mth and not normalize_sha256(root_low):
        errs.append("merkle_root_not_full_sha256")
    isas_verified = _check_binaries(bundle, pol, artifact_root, errs)
    subs_ok = 0
    if pol.require_12_subsystems or bundle.subsystems:
        subs_ok, s_errs = check_subsystem_leaves(bundle.subsystems, root_low, pol.verify_rfc6962_mth)
        errs.extend(s_errs)
    atks_ok = 0
    rejs = 0
    if pol.require_8_attacks or bundle.attacks:
        atks_ok, rejs, a_errs = check_v2_attacks(bundle.attacks)
        errs.extend(a_errs)
    return _seal(not errs, root_low, subs_ok, isas_verified, atks_ok, rejs, errs)


def verify_buildos_v2_file(
    path: Path,
    supplement_path: Path | None = None,
    policy: BuildOSV2Policy | None = None,
    artifact_root: Path | None = None,
) -> BuildOSV2Report:
    """Load and verify a BuildOS-2.0 JSON receipt or bundle from disk."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    supp = json.loads(supplement_path.read_text(encoding="utf-8")) if supplement_path else None
    if isinstance(raw, dict) and raw.get("schema") == "engine-receipt/1":
        bundle = parse_buildos_v2_receipt(raw, supplement=supp)
    else:
        bundle = parse_buildos_v2_payload(raw)
    return verify_buildos_v2_bundle(bundle, policy=policy, artifact_root=artifact_root)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point returning 0 on PASS and 2 on REJECT."""
    parser = argparse.ArgumentParser(description="Verify BuildOS-2.0 sovereign receipts.")
    parser.add_argument("input_json", type=Path)
    parser.add_argument("--supplement", type=Path, default=None)
    parser.add_argument("--artifact-root", type=Path, default=None)
    parser.add_argument("--check-on-disk", action="store_true")
    parser.add_argument("--receipt-only", action="store_true")
    args = parser.parse_args(argv)
    pol = BuildOSV2Policy(
        check_on_disk=args.check_on_disk,
        require_12_subsystems=not args.receipt_only,
        require_8_attacks=not args.receipt_only,
        verify_rfc6962_mth=not args.receipt_only,
    )
    rep = verify_buildos_v2_file(
        args.input_json,
        supplement_path=args.supplement,
        policy=pol,
        artifact_root=args.artifact_root,
    )
    print(json.dumps(asdict(rep), indent=2, sort_keys=True))
    return 0 if rep.ok else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

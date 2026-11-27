# SPDX-License-Identifier: MIT
"""Fail-closed oracle for Slice 34 ZK Pedersen and Slice 35 BuildOS-2.1 Cluster."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import sys
from typing import Sequence

from harness.zk_pedersen_attest.zk_guards import (
    REQUIRED_CLUSTER_ATTACKS,
    REQUIRED_ISAS,
    REQUIRED_ZK_ATTACKS,
    check_attack_controls,
    check_cluster_pillars,
    check_pedersen_conservation,
    is_sha256_hex,
    is_strict_int,
    sha256_file,
)
from harness.zk_pedersen_attest.zk_parser import (
    ZkPedersenBundle,
    parse_zk_payload,
    parse_zk_receipt,
)


@dataclass(frozen=True)
class ZkPedersenPolicy:
    """Configurable policy for Slice 34 ZK Pedersen and Slice 35 Cluster verification."""

    require_all_5_isas: bool = True
    require_attacks: bool = True
    verify_cluster_mth: bool = False
    check_on_disk: bool = False
    max_wasm_bytes: int = 81920


@dataclass(frozen=True)
class ZkPedersenReport:
    """Deterministic fail-closed verdict emitted by zk_pedersen_attest."""

    ok: bool
    verdict: str
    mode: str
    root_hex: str
    curve_eqs: int
    isas_verified: tuple[str, ...]
    attacks_verified: int
    total_attack_rejections: int
    errors: tuple[str, ...]
    report_sha256: str


def _seal(
    ok: bool, mode: str, root: str, eqs: int,
    isas: list[str], atks: int, rejs: int, errs: list[str],
) -> ZkPedersenReport:
    verdict = "PASS" if ok else "REJECT"
    body = {
        "ok": ok, "verdict": verdict, "mode": mode, "root_hex": root,
        "curve_eqs": eqs, "isas_verified": sorted(isas),
        "attacks_verified": atks, "total_attack_rejections": rejs, "errors": list(errs),
    }
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return ZkPedersenReport(ok, verdict, mode, root, eqs, tuple(sorted(isas)), atks, rejs, tuple(errs), digest)


def _check_binaries(
    bundle: ZkPedersenBundle, pol: ZkPedersenPolicy, root: Path | None, errs: list[str]
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
        if pol.check_on_disk and root is not None:
            fp = root / rec.rel_path
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


def verify_zk_pedersen_bundle(
    bundle: ZkPedersenBundle,
    policy: ZkPedersenPolicy | None = None,
    artifact_root: Path | None = None,
) -> ZkPedersenReport:
    """Verify Slice 34 ZK Pedersen or Slice 35 BuildOS-2.1 cluster fail-closed."""
    pol = policy or ZkPedersenPolicy()
    errs: list[str] = list(bundle.parse_errors)
    if bundle.verdict not in ("MATCH", "PASS"):
        errs.append(f"invalid_verdict:{bundle.verdict}")
    if not is_strict_int(bundle.oracle_exit_code) or bundle.oracle_exit_code != 0:
        errs.append(f"nonzero_oracle_exit:{bundle.oracle_exit_code}")
    if not is_sha256_hex(bundle.claim_sha256):
        errs.append("invalid_claim_sha256")
    if not is_sha256_hex(bundle.root_hex):
        errs.append("invalid_root_hex")
    if bundle.mode == "cluster_v21":
        errs.extend(check_cluster_pillars(bundle.pillars, bundle.curve_eqs, bundle.pillar_roots, bundle.root_hex, pol.verify_cluster_mth))
        req_atks = REQUIRED_CLUSTER_ATTACKS
    elif bundle.mode == "zk_pedersen":
        errs.extend(check_pedersen_conservation(bundle.v_in, bundle.v_out1, bundle.v_out2, bundle.verified))
        for k in ("nums_H_hex", "c_in_hex", "excess_D_hex", "schnorr_pt_hex"):
            if not is_sha256_hex(bundle.aux_hex.get(k, "")):
                errs.append(f"invalid_{k}")
        req_atks = REQUIRED_ZK_ATTACKS
    else:
        errs.append(f"unknown_mode:{bundle.mode}")
        req_atks = REQUIRED_ZK_ATTACKS
    isas_ok = _check_binaries(bundle, pol, artifact_root, errs)
    atks_ok, rejs = 0, 0
    if pol.require_attacks or bundle.attacks:
        atks_ok, rejs, a_errs = check_attack_controls(bundle.attacks, req_atks)
        errs.extend(a_errs)
    eqs_i = bundle.curve_eqs if is_strict_int(bundle.curve_eqs) else 0
    return _seal(not errs, bundle.mode, bundle.root_hex, eqs_i, isas_ok, atks_ok, rejs, errs)


def verify_zk_pedersen_file(
    path: Path,
    supplement_path: Path | None = None,
    policy: ZkPedersenPolicy | None = None,
    artifact_root: Path | None = None,
) -> ZkPedersenReport:
    """Load and verify a Slice 34/35 JSON receipt or payload from disk."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    supp = json.loads(supplement_path.read_text(encoding="utf-8")) if supplement_path else None
    bundle = parse_zk_receipt(raw, supp) if isinstance(raw, dict) and raw.get("schema") == "engine-receipt/1" else parse_zk_payload(raw)
    return verify_zk_pedersen_bundle(bundle, policy=policy, artifact_root=artifact_root)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point returning 0 on PASS and 2 on REJECT."""
    parser = argparse.ArgumentParser(description="Verify Slice 34 ZK Pedersen and Slice 35 BuildOS-2.1.")
    parser.add_argument("input_json", type=Path)
    parser.add_argument("--supplement", type=Path, default=None)
    parser.add_argument("--artifact-root", type=Path, default=None)
    parser.add_argument("--check-on-disk", action="store_true")
    parser.add_argument("--receipt-only", action="store_true")
    args = parser.parse_args(argv)
    pol = ZkPedersenPolicy(check_on_disk=args.check_on_disk, require_attacks=not args.receipt_only)
    rep = verify_zk_pedersen_file(args.input_json, args.supplement, pol, args.artifact_root)
    print(json.dumps(asdict(rep), indent=2, sort_keys=True))
    return 0 if rep.ok else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

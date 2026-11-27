# SPDX-License-Identifier: MIT
"""Fail-closed oracle for Slice 33 Zero-C 5-ISA 4-Node Ed25519 BFT Consensus."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import sys
from typing import Sequence

from harness.bft_consensus_attest.bft_guards import (
    BFT_MIN_QUORUM,
    BFT_NODES,
    REQUIRED_ISAS,
    check_bft_attacks,
    check_bft_quorum_votes,
    is_sha256_hex,
    is_strict_int,
    normalize_sha256,
    rfc6962_mth,
    sha256_file,
)
from harness.bft_consensus_attest.bft_parser import (
    BftConsensusBundle,
    parse_bft_payload,
    parse_bft_receipt,
)


@dataclass(frozen=True)
class BftPolicy:
    """Configurable verification policy for Slice 33 BFT Consensus."""

    expected_nodes: int = BFT_NODES
    min_quorum: int = BFT_MIN_QUORUM
    require_all_5_isas: bool = True
    require_4_attacks: bool = True
    require_votes: bool = True
    verify_rfc6962_mth: bool = True
    check_on_disk: bool = False
    max_wasm_bytes: int = 49152


@dataclass(frozen=True)
class BftReport:
    """Deterministic fail-closed verdict emitted by bft_consensus_attest."""

    ok: bool
    verdict: str
    ledger_root_hex: str
    nodes: int
    quorum: int
    valid_sigs: int
    isas_verified: tuple[str, ...]
    attacks_verified: int
    total_attack_rejections: int
    errors: tuple[str, ...]
    report_sha256: str


def _seal(
    ok: bool, root: str, nodes: int, quorum: int, sigs: int,
    isas: list[str], atks: int, rejs: int, errs: list[str],
) -> BftReport:
    verdict = "PASS" if ok else "REJECT"
    body = {
        "ok": ok, "verdict": verdict, "ledger_root_hex": root,
        "nodes": nodes, "quorum": quorum, "valid_sigs": sigs,
        "isas_verified": sorted(isas), "attacks_verified": atks,
        "total_attack_rejections": rejs, "errors": list(errs),
    }
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return BftReport(ok, verdict, root, nodes, quorum, sigs, tuple(sorted(isas)), atks, rejs, tuple(errs), digest)


def _check_binaries(
    bundle: BftConsensusBundle, pol: BftPolicy, root: Path | None, errs: list[str]
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


def verify_bft_bundle(
    bundle: BftConsensusBundle,
    policy: BftPolicy | None = None,
    artifact_root: Path | None = None,
) -> BftReport:
    """Verify a Slice 33 BFT Consensus bundle fail-closed."""
    pol = policy or BftPolicy()
    errs: list[str] = list(bundle.parse_errors)
    if bundle.verdict not in ("MATCH", "PASS"):
        errs.append(f"invalid_verdict:{bundle.verdict}")
    if not is_strict_int(bundle.oracle_exit_code) or bundle.oracle_exit_code != 0:
        errs.append(f"nonzero_oracle_exit:{bundle.oracle_exit_code}")
    for name, hx in (("claim_sha256", bundle.claim_sha256), ("blk3_hex", bundle.blk3_hex), ("ledger_root_hex", bundle.ledger_root_hex)):
        if not is_sha256_hex(hx):
            errs.append(f"invalid_{name}")
    if not is_strict_int(bundle.nodes) or bundle.nodes != pol.expected_nodes:
        errs.append(f"invalid_bft_nodes:{bundle.nodes!r}")
    if not is_strict_int(bundle.quorum) or bundle.quorum < pol.min_quorum or bundle.quorum > pol.expected_nodes:
        errs.append(f"invalid_bft_quorum:{bundle.quorum!r}")
    if bundle.log_leaves_hex is not None and pol.verify_rfc6962_mth:
        leaf_bytes = [bytes.fromhex(n) for h in bundle.log_leaves_hex if (n := normalize_sha256(h))]
        if len(leaf_bytes) != len(bundle.log_leaves_hex) or len(leaf_bytes) < 4:
            errs.append("invalid_log_leaves_hex")
        elif rfc6962_mth(leaf_bytes).hex() != bundle.ledger_root_hex:
            errs.append("rfc6962_ledger_root_mismatch")
    valid_sigs = 0
    if pol.require_votes or bundle.votes:
        valid_sigs, v_errs = check_bft_quorum_votes(bundle.votes, bundle.blk3_hex, pol.expected_nodes, pol.min_quorum)
        errs.extend(v_errs)
    isas_ok = _check_binaries(bundle, pol, artifact_root, errs)
    atks_ok, rejs = 0, 0
    if pol.require_4_attacks or bundle.attacks:
        atks_ok, rejs, a_errs = check_bft_attacks(bundle.attacks)
        errs.extend(a_errs)
    n_i = bundle.nodes if is_strict_int(bundle.nodes) else -1
    q_i = bundle.quorum if is_strict_int(bundle.quorum) else -1
    return _seal(not errs, bundle.ledger_root_hex, n_i, q_i, valid_sigs, isas_ok, atks_ok, rejs, errs)


def verify_bft_file(
    path: Path,
    supplement_path: Path | None = None,
    policy: BftPolicy | None = None,
    artifact_root: Path | None = None,
) -> BftReport:
    """Load and verify a Slice 33 BFT Consensus receipt or bundle from disk."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    supp = json.loads(supplement_path.read_text(encoding="utf-8")) if supplement_path else None
    bundle = parse_bft_receipt(raw, supp) if isinstance(raw, dict) and raw.get("schema") == "engine-receipt/1" else parse_bft_payload(raw)
    return verify_bft_bundle(bundle, policy=policy, artifact_root=artifact_root)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point returning 0 on PASS and 2 on REJECT."""
    parser = argparse.ArgumentParser(description="Verify Slice 33 BFT Consensus receipts.")
    parser.add_argument("input_json", type=Path)
    parser.add_argument("--supplement", type=Path, default=None)
    parser.add_argument("--artifact-root", type=Path, default=None)
    parser.add_argument("--check-on-disk", action="store_true")
    parser.add_argument("--receipt-only", action="store_true")
    args = parser.parse_args(argv)
    pol = BftPolicy(
        check_on_disk=args.check_on_disk,
        require_4_attacks=not args.receipt_only,
        require_votes=not args.receipt_only,
        verify_rfc6962_mth=not args.receipt_only,
    )
    rep = verify_bft_file(args.input_json, args.supplement, pol, args.artifact_root)
    print(json.dumps(asdict(rep), indent=2, sort_keys=True))
    return 0 if rep.ok else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

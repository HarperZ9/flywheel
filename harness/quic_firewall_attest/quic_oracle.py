# SPDX-License-Identifier: MIT
"""Fail-closed attestation oracle for Slice 31 Zero-C QUIC-Lite and CAP_NET_PEER firewall."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import sys
from typing import Sequence

from harness.quic_firewall_attest.quic_guards import (
    REQUIRED_ISAS,
    check_cap_net_peer_rules,
    check_net_attacks,
    check_replay_window_sequence,
    is_sha256_hex,
    is_strict_int,
    sha256_file,
)
from harness.quic_firewall_attest.quic_parser import (
    QuicFirewallBundle,
    parse_quic_payload,
    parse_quic_receipt,
)


@dataclass(frozen=True)
class QuicFirewallPolicy:
    """Configurable policy for Slice 31 QUIC-Lite and firewall verification."""

    require_all_5_isas: bool = True
    require_4_attacks: bool = True
    require_firewall_rules: bool = True
    check_on_disk: bool = False
    max_wasm_bytes: int = 32768


@dataclass(frozen=True)
class QuicFirewallReport:
    """Deterministic fail-closed verdict emitted by quic_firewall_attest."""

    ok: bool
    verdict: str
    quic_root_hex: str
    cwnd: int
    max_pn: int
    isas_verified: tuple[str, ...]
    attacks_verified: int
    total_attack_rejections: int
    errors: tuple[str, ...]
    report_sha256: str


def _seal(
    ok: bool,
    root: str,
    cwnd: int,
    max_pn: int,
    isas: list[str],
    atks: int,
    rejs: int,
    errs: list[str],
) -> QuicFirewallReport:
    verdict = "PASS" if ok else "REJECT"
    body = {
        "ok": ok,
        "verdict": verdict,
        "quic_root_hex": root,
        "cwnd": cwnd,
        "max_pn": max_pn,
        "isas_verified": sorted(isas),
        "attacks_verified": atks,
        "total_attack_rejections": rejs,
        "errors": list(errs),
    }
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return QuicFirewallReport(
        ok=ok,
        verdict=verdict,
        quic_root_hex=root,
        cwnd=cwnd,
        max_pn=max_pn,
        isas_verified=tuple(sorted(isas)),
        attacks_verified=atks,
        total_attack_rejections=rejs,
        errors=tuple(errs),
        report_sha256=digest,
    )


def _check_binaries(
    bundle: QuicFirewallBundle,
    pol: QuicFirewallPolicy,
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


def verify_quic_firewall_bundle(
    bundle: QuicFirewallBundle,
    policy: QuicFirewallPolicy | None = None,
    artifact_root: Path | None = None,
) -> QuicFirewallReport:
    """Verify a Slice 31 QUIC-Lite + CAP_NET_PEER bundle fail-closed."""
    pol = policy or QuicFirewallPolicy()
    errs: list[str] = list(bundle.parse_errors)
    if bundle.verdict not in ("MATCH", "PASS"):
        errs.append(f"invalid_verdict:{bundle.verdict}")
    if not is_strict_int(bundle.oracle_exit_code) or bundle.oracle_exit_code != 0:
        errs.append(f"nonzero_oracle_exit:{bundle.oracle_exit_code}")
    for label, digest in (
        ("claim_sha256", bundle.claim_sha256),
        ("quic_root_hex", bundle.quic_root_hex),
        ("tx_sha_hex", bundle.tx_sha_hex),
        ("fw_sha_hex", bundle.fw_sha_hex),
    ):
        if not is_sha256_hex(digest):
            errs.append(f"invalid_{label}")
    if not is_strict_int(bundle.cwnd) or bundle.cwnd <= 0:
        errs.append(f"invalid_cwnd:{bundle.cwnd!r}")
    if not is_strict_int(bundle.max_pn) or bundle.max_pn < 0:
        errs.append(f"invalid_max_pn:{bundle.max_pn!r}")
    if bundle.packet_numbers is not None:
        sim_max, sim_bmp, pn_errs = check_replay_window_sequence(bundle.packet_numbers)
        errs.extend(pn_errs)
        if not pn_errs and is_strict_int(bundle.max_pn) and sim_max != bundle.max_pn:
            errs.append(f"max_pn_mismatch:{sim_max}!={bundle.max_pn}")
        if not pn_errs and is_strict_int(bundle.bmp_lo) and sim_bmp != bundle.bmp_lo:
            errs.append(f"bmp_lo_mismatch:{sim_bmp}!={bundle.bmp_lo}")
    if pol.require_firewall_rules or bundle.firewall_default is not None or bundle.firewall_rules:
        errs.extend(check_cap_net_peer_rules(bundle.firewall_default, bundle.firewall_rules))
    isas_ok = _check_binaries(bundle, pol, artifact_root, errs)
    atks_ok, rejs = 0, 0
    if pol.require_4_attacks or bundle.attacks:
        atks_ok, rejs, a_errs = check_net_attacks(bundle.attacks)
        errs.extend(a_errs)
    cwnd_i = bundle.cwnd if is_strict_int(bundle.cwnd) else -1
    pn_i = bundle.max_pn if is_strict_int(bundle.max_pn) else -1
    return _seal(not errs, bundle.quic_root_hex, cwnd_i, pn_i, isas_ok, atks_ok, rejs, errs)


def verify_quic_firewall_file(
    path: Path,
    supplement_path: Path | None = None,
    policy: QuicFirewallPolicy | None = None,
    artifact_root: Path | None = None,
) -> QuicFirewallReport:
    """Load and verify a Slice 31 QUIC-Lite receipt or bundle from disk."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    supp = json.loads(supplement_path.read_text(encoding="utf-8")) if supplement_path else None
    if isinstance(raw, dict) and raw.get("schema") == "engine-receipt/1":
        bundle = parse_quic_receipt(raw, supplement=supp)
    else:
        bundle = parse_quic_payload(raw)
    return verify_quic_firewall_bundle(bundle, policy=policy, artifact_root=artifact_root)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point returning 0 on PASS and 2 on REJECT."""
    parser = argparse.ArgumentParser(description="Verify Slice 31 QUIC-Lite + firewall receipts.")
    parser.add_argument("input_json", type=Path)
    parser.add_argument("--supplement", type=Path, default=None)
    parser.add_argument("--artifact-root", type=Path, default=None)
    parser.add_argument("--check-on-disk", action="store_true")
    parser.add_argument("--receipt-only", action="store_true")
    args = parser.parse_args(argv)
    pol = QuicFirewallPolicy(
        check_on_disk=args.check_on_disk,
        require_4_attacks=not args.receipt_only,
        require_firewall_rules=not args.receipt_only,
    )
    rep = verify_quic_firewall_file(args.input_json, args.supplement, pol, args.artifact_root)
    print(json.dumps(asdict(rep), indent=2, sort_keys=True))
    return 0 if rep.ok else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

# SPDX-License-Identifier: MIT
"""Fail-closed oracle for Slice 32 Zero-C Fuel-Metered Capability Sandbox Bytecode VM."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import sys
from typing import Sequence

from harness.cap_sandbox_vm_gate.vm_guards import (
    CODE_SEG_BASE,
    DEFAULT_MAX_FUEL,
    DEFAULT_MEM_WORDS,
    REQUIRED_ISAS,
    check_vm_attacks,
    check_vm_execution_trace,
    is_sha256_hex,
    is_strict_int,
    sha256_file,
)
from harness.cap_sandbox_vm_gate.vm_parser import (
    CapSandboxVmBundle,
    parse_vm_payload,
    parse_vm_receipt,
)


@dataclass(frozen=True)
class CapVmPolicy:
    """Configurable verification policy for Slice 32 Capability Sandbox VM."""

    max_fuel_budget: int = DEFAULT_MAX_FUEL
    mem_words: int = DEFAULT_MEM_WORDS
    code_seg_base: int = CODE_SEG_BASE
    require_all_5_isas: bool = True
    require_4_attacks: bool = True
    check_on_disk: bool = False
    max_wasm_bytes: int = 32768


@dataclass(frozen=True)
class CapVmReport:
    """Deterministic fail-closed verdict emitted by cap_sandbox_vm_gate."""

    ok: bool
    verdict: str
    vm_root_hex: str
    fuel_budget: int
    fuel_used: int
    cap_mask: int
    isas_verified: tuple[str, ...]
    attacks_verified: int
    total_attack_rejections: int
    errors: tuple[str, ...]
    report_sha256: str


def _seal(
    ok: bool, root: str, budget: int, used: int, cap_mask: int,
    isas: list[str], atks: int, rejs: int, errs: list[str],
) -> CapVmReport:
    verdict = "PASS" if ok else "REJECT"
    body = {
        "ok": ok, "verdict": verdict, "vm_root_hex": root,
        "fuel_budget": budget, "fuel_used": used, "cap_mask": cap_mask,
        "isas_verified": sorted(isas), "attacks_verified": atks,
        "total_attack_rejections": rejs, "errors": list(errs),
    }
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return CapVmReport(ok, verdict, root, budget, used, cap_mask, tuple(sorted(isas)), atks, rejs, tuple(errs), digest)


def _check_binaries(
    bundle: CapSandboxVmBundle, pol: CapVmPolicy, root: Path | None, errs: list[str]
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


def verify_cap_vm_bundle(
    bundle: CapSandboxVmBundle,
    policy: CapVmPolicy | None = None,
    artifact_root: Path | None = None,
) -> CapVmReport:
    """Verify a Slice 32 Fuel-Metered Capability Sandbox VM bundle fail-closed."""
    pol = policy or CapVmPolicy()
    errs: list[str] = list(bundle.parse_errors)
    if bundle.verdict not in ("MATCH", "PASS"):
        errs.append(f"invalid_verdict:{bundle.verdict}")
    if not is_strict_int(bundle.oracle_exit_code) or bundle.oracle_exit_code != 0:
        errs.append(f"nonzero_oracle_exit:{bundle.oracle_exit_code}")
    for name, hx in (("claim_sha256", bundle.claim_sha256), ("guest_sha_hex", bundle.guest_sha_hex), ("trace_sha_hex", bundle.trace_sha_hex), ("vm_root_hex", bundle.vm_root_hex)):
        if not is_sha256_hex(hx):
            errs.append(f"invalid_{name}")
    errs.extend(
        check_vm_execution_trace(
            bundle.fuel_budget, bundle.fuel_used, bundle.cap_mask,
            bundle.mem_writes, bundle.hostcalls,
            pol.max_fuel_budget, pol.mem_words, pol.code_seg_base,
        )
    )
    isas_ok = _check_binaries(bundle, pol, artifact_root, errs)
    atks_ok, rejs = 0, 0
    if pol.require_4_attacks or bundle.attacks:
        atks_ok, rejs, a_errs = check_vm_attacks(bundle.attacks)
        errs.extend(a_errs)
    fb = bundle.fuel_budget if is_strict_int(bundle.fuel_budget) else -1
    fu = bundle.fuel_used if is_strict_int(bundle.fuel_used) else -1
    cm = bundle.cap_mask if is_strict_int(bundle.cap_mask) else -1
    return _seal(not errs, bundle.vm_root_hex, fb, fu, cm, isas_ok, atks_ok, rejs, errs)


def verify_cap_vm_file(
    path: Path,
    supplement_path: Path | None = None,
    policy: CapVmPolicy | None = None,
    artifact_root: Path | None = None,
) -> CapVmReport:
    """Load and verify a Slice 32 Sandbox VM receipt or bundle from disk."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    supp = json.loads(supplement_path.read_text(encoding="utf-8")) if supplement_path else None
    bundle = parse_vm_receipt(raw, supp) if isinstance(raw, dict) and raw.get("schema") == "engine-receipt/1" else parse_vm_payload(raw)
    return verify_cap_vm_bundle(bundle, policy=policy, artifact_root=artifact_root)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point returning 0 on PASS and 2 on REJECT."""
    parser = argparse.ArgumentParser(description="Verify Slice 32 Capability Sandbox VM receipts.")
    parser.add_argument("input_json", type=Path)
    parser.add_argument("--supplement", type=Path, default=None)
    parser.add_argument("--artifact-root", type=Path, default=None)
    parser.add_argument("--check-on-disk", action="store_true")
    parser.add_argument("--receipt-only", action="store_true")
    args = parser.parse_args(argv)
    pol = CapVmPolicy(
        check_on_disk=args.check_on_disk,
        require_4_attacks=not args.receipt_only,
    )
    rep = verify_cap_vm_file(args.input_json, args.supplement, pol, args.artifact_root)
    print(json.dumps(asdict(rep), indent=2, sort_keys=True))
    return 0 if rep.ok else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

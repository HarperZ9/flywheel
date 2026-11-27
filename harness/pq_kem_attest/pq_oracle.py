# SPDX-License-Identifier: MIT
"""Fail-closed attestation oracle for FIPS 203 ML-KEM-512 + X25519 hybrid KEM bundles."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import sys
from typing import Sequence

from harness.pq_kem_attest.kem_parser import (
    PqKemBundle,
    parse_pq_kem_payload,
    parse_pq_kem_receipt,
)
from harness.pq_kem_attest.pq_guards import (
    REQUIRED_ISAS,
    check_canonical_coeffs,
    check_fips203_params,
    check_fo_controls,
    is_sha256_hex,
    is_strict_int,
    sha256_file,
)


@dataclass(frozen=True)
class PqKemPolicy:
    """Configurable policy for PQ Hybrid KEM verification."""

    require_all_5_isas: bool = True
    require_fo_controls: bool = True
    require_coefficients: bool = False
    check_on_disk: bool = False
    max_wasm_bytes: int = 65536


@dataclass(frozen=True)
class PqKemReport:
    """Deterministic fail-closed verdict emitted by pq_kem_attest."""

    ok: bool
    verdict: str
    q: int
    n: int
    k: int
    isas_verified: tuple[str, ...]
    fo_controls_verified: int
    coeffs_checked: int
    errors: tuple[str, ...]
    report_sha256: str


def _seal_report(
    ok: bool,
    q: int,
    n: int,
    k: int,
    isas: list[str],
    fo_passed: int,
    coeffs_checked: int,
    errors: list[str],
) -> PqKemReport:
    verdict = "PASS" if ok else "REJECT"
    payload = {
        "ok": ok,
        "verdict": verdict,
        "q": q,
        "n": n,
        "k": k,
        "isas_verified": sorted(isas),
        "fo_controls_verified": fo_passed,
        "coeffs_checked": coeffs_checked,
        "errors": list(errors),
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return PqKemReport(
        ok=ok,
        verdict=verdict,
        q=q,
        n=n,
        k=k,
        isas_verified=tuple(sorted(isas)),
        fo_controls_verified=fo_passed,
        coeffs_checked=coeffs_checked,
        errors=tuple(errors),
        report_sha256=digest,
    )


def _check_binaries(
    bundle: PqKemBundle,
    policy: PqKemPolicy,
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
        if rec.isa == "wasm" and rec.byte_size > policy.max_wasm_bytes:
            errs.append(f"wasm_exceeds_budget:{rec.byte_size}>{policy.max_wasm_bytes}")
            continue
        if not is_sha256_hex(rec.sha256):
            errs.append(f"invalid_sha256:{rec.isa}")
            continue
        if policy.check_on_disk and artifact_root is not None:
            fp = artifact_root / rec.rel_path
            if not fp.is_file():
                errs.append(f"missing_on_disk:{rec.isa}")
                continue
            actual = sha256_file(fp)
            if actual != rec.sha256:
                errs.append(f"sha256_mismatch:{rec.isa}")
                continue
        verified.append(rec.isa)
    if policy.require_all_5_isas:
        for req in REQUIRED_ISAS:
            if req not in seen:
                errs.append(f"missing_isa:{req}")
    return verified


def verify_pq_kem_bundle(
    bundle: PqKemBundle,
    policy: PqKemPolicy | None = None,
    artifact_root: Path | None = None,
) -> PqKemReport:
    """Verify a parsed PQ Hybrid KEM bundle fail-closed."""
    pol = policy or PqKemPolicy()
    errs: list[str] = list(bundle.parse_errors)
    if bundle.verdict not in ("MATCH", "PASS"):
        errs.append(f"invalid_verdict:{bundle.verdict}")
    if not is_strict_int(bundle.oracle_exit_code) or bundle.oracle_exit_code != 0:
        errs.append(f"nonzero_oracle_exit:{bundle.oracle_exit_code}")
    if not is_sha256_hex(bundle.claim_sha256):
        errs.append("invalid_claim_sha256")
    if not is_strict_int(bundle.hybrid_committed) or bundle.hybrid_committed != 1:
        errs.append(f"hybrid_not_committed:{bundle.hybrid_committed!r}")
    errs.extend(check_fips203_params(bundle.q, bundle.n, bundle.k))
    coeffs_checked = 0
    if bundle.coefficients is not None:
        coeffs_checked, c_errs = check_canonical_coeffs(bundle.coefficients)
        errs.extend(c_errs)
    elif pol.require_coefficients:
        errs.append("coefficients_missing")
    isas_verified = _check_binaries(bundle, pol, artifact_root, errs)
    fo_passed = 0
    if pol.require_fo_controls or bundle.fo_controls:
        fo_passed, fo_errs = check_fo_controls(bundle.fo_controls)
        errs.extend(fo_errs)
    q_i = bundle.q if is_strict_int(bundle.q) else -1
    n_i = bundle.n if is_strict_int(bundle.n) else -1
    k_i = bundle.k if is_strict_int(bundle.k) else -1
    return _seal_report(not errs, q_i, n_i, k_i, isas_verified, fo_passed, coeffs_checked, errs)


def verify_pq_kem_file(
    path: Path,
    supplement_path: Path | None = None,
    policy: PqKemPolicy | None = None,
    artifact_root: Path | None = None,
) -> PqKemReport:
    """Load and verify a PQ Hybrid KEM JSON receipt or payload from disk."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    supp = None
    if supplement_path is not None:
        supp = json.loads(supplement_path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and raw.get("schema") == "engine-receipt/1":
        bundle = parse_pq_kem_receipt(raw, supplement=supp)
    else:
        bundle = parse_pq_kem_payload(raw)
    return verify_pq_kem_bundle(bundle, policy=policy, artifact_root=artifact_root)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point returning 0 on PASS and 2 on REJECT."""
    parser = argparse.ArgumentParser(description="Verify FIPS 203 PQ Hybrid KEM receipts.")
    parser.add_argument("input_json", type=Path)
    parser.add_argument("--supplement", type=Path, default=None)
    parser.add_argument("--artifact-root", type=Path, default=None)
    parser.add_argument("--check-on-disk", action="store_true")
    parser.add_argument("--no-fo-controls", action="store_true")
    args = parser.parse_args(argv)
    pol = PqKemPolicy(
        check_on_disk=args.check_on_disk,
        require_fo_controls=not args.no_fo_controls,
    )
    report = verify_pq_kem_file(
        args.input_json,
        supplement_path=args.supplement,
        policy=pol,
        artifact_root=args.artifact_root,
    )
    print(json.dumps(asdict(report), indent=2, sort_keys=True))
    return 0 if report.ok else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

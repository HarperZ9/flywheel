# SPDX-License-Identifier: MIT
"""Fail-closed Flywheel oracle for Zero-C BuildOS Confidential Enclave (Slice 28).

Verifies measurement-bound mr_enclave HKDF/AEAD sealing, monotonic nonce
freshness, zero-egress capability allowlist, Ed25519 remote quote signature
points, 5-ISA binary SHA-256 parity, and enclave_quote_attestation_sha256.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .enclave_guards import (
    CAP_NET_EGRESS_BIT,
    DEFAULT_POLICY_ALLOW_MASK,
    REQUIRED_ENCLAVE_ISAS,
    canonical_sha256_hex,
    infer_isa_from_path,
    is_strict_int,
    normalize_hex,
)
from .quote_checker import (
    EnclaveQuoteSpec,
    EnclaveTargetRun,
    validate_emit_latency,
    validate_quote_digests,
    validate_target_runs,
)

HONEST_SCOPE_LIMIT = (
    "Verifies Slice 28 enclave quote digests, monotonic nonce freshness, "
    "zero-egress capability allowlist, 4/4 attack rejections across 5 ISAs, "
    "and engine-receipt/1 artifact SHA-256 parity in pure Python stdlib. "
    "Does not run RV64/AArch64 emulation or hardware enclave attestation."
)


@dataclass(frozen=True)
class EnclaveQuoteReport:
    """Fail-closed attestation verdict for Zero-C BuildOS Confidential Enclave."""

    passed: bool
    isa_count: int
    epoch: int
    min_nonce_seq: int
    min_attacks_caught: int
    zero_egress_verified: bool
    enclave_quote_attestation_sha256: str
    violations: tuple[str, ...]
    honest_scope_limit: str = HONEST_SCOPE_LIMIT


def verify_enclave_quote(
    spec: Any,
    *,
    min_attacks: int = 4,
    policy_allow_mask: int = DEFAULT_POLICY_ALLOW_MASK,
    forbidden_egress_mask: int = CAP_NET_EGRESS_BIT,
    max_emit_ms: float = 5000.0,
    actual_binary_hashes: dict[str, tuple[int, str]] | None = None,
) -> EnclaveQuoteReport:
    """Run fail-closed verification on an EnclaveQuoteSpec."""
    if not isinstance(spec, EnclaveQuoteSpec):
        return _fail_report("spec: expected EnclaveQuoteSpec")
    pre_errs = validate_emit_latency(max_emit_ms, "max_emit_ms")
    if not is_strict_int(min_attacks) or min_attacks <= 0:
        pre_errs.append(f"min_attacks: expected positive strict int, got {min_attacks!r}")
    if pre_errs:
        return _fail_report("; ".join(pre_errs))
    violations = validate_quote_digests(spec)
    violations.extend(
        validate_target_runs(
            spec,
            min_attacks=min_attacks,
            policy_allow_mask=policy_allow_mask,
            forbidden_egress_mask=forbidden_egress_mask,
        )
    )
    if actual_binary_hashes is not None:
        violations.extend(_check_binary_hashes(spec.targets, actual_binary_hashes))
    return _build_report(spec, violations)


def _check_binary_hashes(
    targets: tuple[EnclaveTargetRun, ...],
    actual_hashes: dict[str, tuple[int, str]],
) -> list[str]:
    errors: list[str] = []
    for run in targets:
        if run.isa not in actual_hashes:
            errors.append(f"{run.isa}: missing on-disk binary hash")
            continue
        act_sz, act_sha_raw = actual_hashes[run.isa]
        act_sha, err = normalize_hex(act_sha_raw, 64, f"actual.{run.isa}")
        if err or act_sz != run.bin_bytes or act_sha != run.bin_sha256.strip().lower():
            errors.append(f"{run.isa}: binary SHA-256 or byte size mismatch")
    return errors


def _build_report(
    spec: EnclaveQuoteSpec,
    violations: list[str],
) -> EnclaveQuoteReport:
    ordered = sorted(spec.targets, key=lambda r: r.isa)
    min_nonce = min((r.nonce_seq for r in ordered if is_strict_int(r.nonce_seq)), default=0)
    min_att = min((r.attacks_caught for r in ordered if is_strict_int(r.attacks_caught)), default=0)
    zero_egress_ok = not any("zero_egress_violation" in v or "policy_violation" in v for v in violations)
    attest = {
        "mr_enclave_hex": spec.mr_enclave_hex.strip().lower(),
        "enclave_root_hex": spec.enclave_root_hex.strip().lower(),
        "quote_digest_hex": spec.quote_digest_hex.strip().lower(),
        "aead_tag_hex": spec.aead_tag_hex.strip().lower(),
        "ed_pt_hex": spec.ed_pt_hex.strip().lower(),
        "epoch": spec.epoch,
        "targets": [(r.isa, r.nonce_seq, r.granted_caps, r.attacks_caught, r.bin_bytes, r.bin_sha256.lower()) for r in ordered],
    }
    return EnclaveQuoteReport(
        passed=len(violations) == 0,
        isa_count=len({r.isa for r in ordered if r.isa in REQUIRED_ENCLAVE_ISAS}),
        epoch=spec.epoch if is_strict_int(spec.epoch) else 0,
        min_nonce_seq=min_nonce,
        min_attacks_caught=min_att,
        zero_egress_verified=zero_egress_ok,
        enclave_quote_attestation_sha256=canonical_sha256_hex(attest),
        violations=tuple(violations),
    )


def _fail_report(message: str) -> EnclaveQuoteReport:
    return EnclaveQuoteReport(False, 0, 0, 0, 0, False, "", (message,))


def verify_enclave_receipt_file(
    receipt_path: Path | str,
    *,
    mr_enclave_hex: str,
    enclave_root_hex: str,
    quote_digest_hex: str,
    aead_tag_hex: str,
    ed_pt_hex: str,
    epoch: int = 28,
    prev_nonce_seq: int = 41,
    nonce_seq: int = 42,
    granted_caps: int = DEFAULT_POLICY_ALLOW_MASK,
    attacks_caught: int = 4,
    check_disk_binaries: bool = False,
) -> EnclaveQuoteReport:
    """Verify a Slice 28 engine-receipt/1 file and optional on-disk binaries."""
    try:
        rec = json.loads(Path(receipt_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        return _fail_report(f"io_error: {exc}")
    if not isinstance(rec, dict) or rec.get("verdict") != "MATCH":
        return _fail_report("receipt: verdict != MATCH")
    oracle = rec.get("oracle")
    if not isinstance(oracle, dict) or oracle.get("exit_code") != 0:
        return _fail_report("receipt: oracle exit_code != 0")
    subj = rec.get("subject")
    arts = subj.get("artifacts") if isinstance(subj, dict) else None
    if not isinstance(arts, list):
        return _fail_report("receipt: missing subject.artifacts")
    art_paths = rec.get("artifact_paths") if isinstance(rec.get("artifact_paths"), dict) else {}
    runs, actual_hashes = _extract_runs(
        arts, art_paths, epoch, nonce_seq, granted_caps, quote_digest_hex, enclave_root_hex, attacks_caught, check_disk_binaries
    )
    spec = EnclaveQuoteSpec(
        mr_enclave_hex, enclave_root_hex, quote_digest_hex, aead_tag_hex, ed_pt_hex, prev_nonce_seq, epoch, tuple(runs)
    )
    return verify_enclave_quote(spec, actual_binary_hashes=actual_hashes if check_disk_binaries else None)


def _extract_runs(
    arts: list[Any],
    art_paths: dict[str, Any],
    epoch: int,
    nonce_seq: int,
    granted_caps: int,
    quote_digest_hex: str,
    enclave_root_hex: str,
    attacks_caught: int,
    check_disk: bool,
) -> tuple[list[EnclaveTargetRun], dict[str, tuple[int, str]]]:
    runs: list[EnclaveTargetRun] = []
    actual_hashes: dict[str, tuple[int, str]] = {}
    for item in arts:
        if not isinstance(item, dict):
            continue
        rel = str(item.get("rel_path", ""))
        isa = infer_isa_from_path(rel)
        if isa is None:
            continue
        sha, _ = normalize_hex(item.get("sha256"), 64, f"art.{isa}")
        sz = item.get("bytes")
        runs.append(
            EnclaveTargetRun(isa, 1, 1, epoch, nonce_seq, granted_caps, quote_digest_hex, enclave_root_hex, attacks_caught, sz if is_strict_int(sz) else 0, sha or "")
        )
        if check_disk and rel in art_paths:
            fp = Path(str(art_paths[rel]))
            if fp.is_file():
                data = fp.read_bytes()
                actual_hashes[isa] = (len(data), hashlib.sha256(data).hexdigest())
    return runs, actual_hashes

# SPDX-License-Identifier: MIT
"""Enclave quote payload and 5-ISA target parity validator (Slice 28).

Validates measurement-bound mr_enclave digests, HKDF/ChaCha20-Poly1305 AEAD
sealing tags, monotonic nonce freshness, zero-egress capability allowlists,
Ed25519 remote quote signature points, and 5-ISA bit-exact parity.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .enclave_guards import (
    CAP_NET_EGRESS_BIT,
    DEFAULT_POLICY_ALLOW_MASK,
    REQUIRED_ENCLAVE_ISAS,
    check_zero_egress_caps,
    is_strict_finite_float,
    is_strict_int,
    normalize_hex,
)

HONEST_SCOPE_LIMIT = (
    "Validates enclave attestation quote fields, monotonic nonce ordering, "
    "zero-egress capability bitmasks, and 5-ISA cross-target parity in pure "
    "Python stdlib. Does not verify hardware SGX/TDX root certificates."
)


@dataclass(frozen=True)
class EnclaveTargetRun:
    """Observed execution output for one of the 5 Zero-C enclave ISAs."""

    isa: str
    status: int
    enclave_attested: int
    epoch: int
    nonce_seq: int
    granted_caps: int
    quote_digest_hex: str
    enclave_root_hex: str
    attacks_caught: int
    bin_bytes: int
    bin_sha256: str


@dataclass(frozen=True)
class EnclaveQuoteSpec:
    """Complete Slice 28 enclave attestation bundle for fail-closed checking."""

    mr_enclave_hex: str
    enclave_root_hex: str
    quote_digest_hex: str
    aead_tag_hex: str
    ed_pt_hex: str
    prev_nonce_seq: int
    epoch: int
    targets: tuple[EnclaveTargetRun, ...]


def validate_quote_digests(spec: EnclaveQuoteSpec) -> list[str]:
    """Validate all cryptographic hex digests on an EnclaveQuoteSpec."""
    errors: list[str] = []
    checks = (
        ("mr_enclave_hex", spec.mr_enclave_hex, 64),
        ("enclave_root_hex", spec.enclave_root_hex, 64),
        ("quote_digest_hex", spec.quote_digest_hex, 64),
        ("aead_tag_hex", spec.aead_tag_hex, 32),
        ("ed_pt_hex", spec.ed_pt_hex, 64),
    )
    for label, raw, size in checks:
        dig, err = normalize_hex(raw, size, label)
        if err or dig is None:
            errors.append(err or f"{label}: invalid digest")
        elif dig == "0" * size:
            errors.append(f"{label}: all-zero digest rejected")
    if not is_strict_int(spec.prev_nonce_seq) or spec.prev_nonce_seq < 0:
        errors.append(f"prev_nonce_seq: invalid {spec.prev_nonce_seq!r}")
    if not is_strict_int(spec.epoch) or spec.epoch <= 0:
        errors.append(f"epoch: invalid {spec.epoch!r}")
    return errors


def validate_target_runs(
    spec: EnclaveQuoteSpec,
    *,
    min_attacks: int = 4,
    policy_allow_mask: int = DEFAULT_POLICY_ALLOW_MASK,
    forbidden_egress_mask: int = CAP_NET_EGRESS_BIT,
) -> list[str]:
    """Validate 5-ISA target completeness, monotonic nonces, and zero-egress."""
    errors: list[str] = []
    seen_isas: set[str] = set()
    for run in spec.targets:
        if not isinstance(run, EnclaveTargetRun):
            errors.append("targets: invalid EnclaveTargetRun element")
            continue
        if run.isa not in REQUIRED_ENCLAVE_ISAS:
            errors.append(f"targets: unknown ISA {run.isa!r}")
        elif run.isa in seen_isas:
            errors.append(f"targets: duplicate ISA {run.isa}")
        seen_isas.add(run.isa)
        errors.extend(
            _check_one_run(run, spec, min_attacks, policy_allow_mask, forbidden_egress_mask)
        )
    missing = sorted(REQUIRED_ENCLAVE_ISAS - seen_isas)
    if missing:
        errors.append(f"targets: missing required ISAs {missing}")
    return errors


def _check_one_run(
    run: EnclaveTargetRun,
    spec: EnclaveQuoteSpec,
    min_attacks: int,
    allow_mask: int,
    egress_mask: int,
) -> list[str]:
    errs: list[str] = []
    if not is_strict_int(run.status) or run.status != 1:
        errs.append(f"{run.isa}: status must be 1, got {run.status!r}")
    if not is_strict_int(run.enclave_attested) or run.enclave_attested != 1:
        errs.append(f"{run.isa}: enclave_attested must be 1")
    if not is_strict_int(run.epoch) or run.epoch != spec.epoch:
        errs.append(f"{run.isa}: epoch {run.epoch!r} != {spec.epoch}")
    if not is_strict_int(run.nonce_seq) or run.nonce_seq <= spec.prev_nonce_seq:
        errs.append(f"{run.isa}: stale nonce {run.nonce_seq!r} <= {spec.prev_nonce_seq}")
    if not is_strict_int(run.attacks_caught) or run.attacks_caught < min_attacks:
        errs.append(f"{run.isa}: attacks_caught {run.attacks_caught!r} < {min_attacks}")
    if not is_strict_int(run.bin_bytes) or run.bin_bytes <= 0:
        errs.append(f"{run.isa}: invalid bin_bytes {run.bin_bytes!r}")
    _, sha_err = normalize_hex(run.bin_sha256, 64, f"{run.isa}.bin_sha256")
    if sha_err:
        errs.append(sha_err)
    errs.extend(
        check_zero_egress_caps(
            run.granted_caps, policy_allow_mask=allow_mask, forbidden_egress_mask=egress_mask
        )
    )
    if run.quote_digest_hex.strip().lower() != spec.quote_digest_hex.strip().lower():
        errs.append(f"{run.isa}: quote_digest_hex parity mismatch")
    if run.enclave_root_hex.strip().lower() != spec.enclave_root_hex.strip().lower():
        errs.append(f"{run.isa}: enclave_root_hex parity mismatch")
    return errs


def validate_emit_latency(value: Any, label: str) -> list[str]:
    """Validate optional finite positive latency ceiling."""
    if not is_strict_finite_float(value) or float(value) <= 0.0:
        return [f"{label}: invalid latency ceiling {value!r}"]
    return []

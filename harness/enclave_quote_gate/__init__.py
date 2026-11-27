# SPDX-License-Identifier: MIT
"""Pure-stdlib Flywheel oracle for Zero-C BuildOS Confidential Enclave (Slice 28).

Verifies measurement-bound mr_enclave HKDF/AEAD sealing, monotonic nonce
freshness, zero-egress capability allowlists, Ed25519 remote quote signature
points, 5-ISA binary parity, and enclave_quote_attestation_sha256 sealing.
"""

from __future__ import annotations

from .enclave_guards import (
    CAP_NET_EGRESS_BIT,
    DEFAULT_POLICY_ALLOW_MASK,
    HEX32_RE,
    HEX64_RE,
    REQUIRED_ENCLAVE_ISAS,
    canonical_sha256_hex,
    check_zero_egress_caps,
    infer_isa_from_path,
    is_strict_finite_float,
    is_strict_int,
    normalize_hex,
    validate_binary_magic,
)
from .enclave_guards import (
    HONEST_SCOPE_LIMIT as GUARDS_HONEST_SCOPE_LIMIT,
)
from .enclave_oracle import (
    HONEST_SCOPE_LIMIT as ORACLE_HONEST_SCOPE_LIMIT,
)
from .enclave_oracle import (
    EnclaveQuoteReport,
    verify_enclave_quote,
    verify_enclave_receipt_file,
)
from .quote_checker import (
    HONEST_SCOPE_LIMIT as CHECKER_HONEST_SCOPE_LIMIT,
)
from .quote_checker import (
    EnclaveQuoteSpec,
    EnclaveTargetRun,
    validate_emit_latency,
    validate_quote_digests,
    validate_target_runs,
)

HONEST_SCOPE_LIMIT = (
    "Pure-Python stdlib fail-closed verifier for Zero-C BuildOS Confidential "
    "Enclave (Slice 28): measurement-bound digests, monotonic nonces, "
    "zero-egress capability masks, 5-ISA parity, and receipt binary SHA-256. "
    "Does not emulate CPUs or perform hardware root-of-trust verification."
)

HONEST_SCOPE_LIMITS: dict[str, str] = {
    "enclave_guards": GUARDS_HONEST_SCOPE_LIMIT,
    "quote_checker": CHECKER_HONEST_SCOPE_LIMIT,
    "enclave_oracle": ORACLE_HONEST_SCOPE_LIMIT,
}

__all__ = [
    "CAP_NET_EGRESS_BIT",
    "DEFAULT_POLICY_ALLOW_MASK",
    "EnclaveQuoteReport",
    "EnclaveQuoteSpec",
    "EnclaveTargetRun",
    "HEX32_RE",
    "HEX64_RE",
    "HONEST_SCOPE_LIMIT",
    "HONEST_SCOPE_LIMITS",
    "REQUIRED_ENCLAVE_ISAS",
    "canonical_sha256_hex",
    "check_zero_egress_caps",
    "infer_isa_from_path",
    "is_strict_finite_float",
    "is_strict_int",
    "normalize_hex",
    "validate_binary_magic",
    "validate_emit_latency",
    "validate_quote_digests",
    "validate_target_runs",
    "verify_enclave_quote",
    "verify_enclave_receipt_file",
]

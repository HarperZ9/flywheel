# SPDX-License-Identifier: MIT
"""Pure-stdlib cryptographic attestation primitives for Flywheel.

Provides three fail-closed verification surfaces:
  1. Multi-ISA cross-target build and output digest parity checking.
  2. RFC 6962 Certificate Transparency Merkle inclusion and consistency proofs.
  3. RFC 8439 ChaCha20-Poly1305 AEAD envelope sealing and verification.
"""

from __future__ import annotations

from .aead_envelope import (
    ENVELOPE_ALG,
    ENVELOPE_SCHEMA,
    KEY_BYTES,
    NONCE_BYTES,
    RFC8439_SECTION_2_8_2_TAG_HEX,
    TAG_BYTES,
    AeadAuthError,
    aead_open,
    aead_seal,
    chacha20_block,
    chacha20_xor,
    open_envelope,
    poly1305_mac,
    seal_envelope,
)
from .aead_envelope import (
    HONEST_SCOPE_LIMIT as AEAD_HONEST_SCOPE_LIMIT,
)
from .merkle_attest import (
    DIGEST_BYTES,
    EMPTY_TREE_HASH,
    LEAF_PREFIX,
    NODE_PREFIX,
    check_domain_separation,
    consistency_proof,
    inclusion_proof,
    leaf_hash,
    merkle_root,
    node_hash,
    verify_consistency,
    verify_inclusion,
)
from .merkle_attest import (
    HONEST_SCOPE_LIMIT as MERKLE_HONEST_SCOPE_LIMIT,
)
from .multi_isa_parity import (
    HONEST_SCOPE_LIMIT as MULTI_ISA_HONEST_SCOPE_LIMIT,
)
from .multi_isa_parity import (
    REQUIRED_TARGETS,
    IsaBuildRecord,
    MultiIsaParityReport,
    build_record_from_bytes,
    sha256_hex,
    verify_multi_isa_parity,
)

HONEST_SCOPE_LIMIT = (
    "Pure-Python stdlib verification harness for multi-ISA build parity, "
    "RFC 6962 Merkle proofs, and RFC 8439 ChaCha20-Poly1305 AEAD envelopes. "
    "Intended for deterministic attestation and CI verification rather than "
    "side-channel-hardened secret custody or hardware ISA emulation."
)

HONEST_SCOPE_LIMITS: dict[str, str] = {
    "multi_isa_parity": MULTI_ISA_HONEST_SCOPE_LIMIT,
    "merkle_attest": MERKLE_HONEST_SCOPE_LIMIT,
    "aead_envelope": AEAD_HONEST_SCOPE_LIMIT,
}

__all__ = [
    "AeadAuthError",
    "DIGEST_BYTES",
    "EMPTY_TREE_HASH",
    "ENVELOPE_ALG",
    "ENVELOPE_SCHEMA",
    "HONEST_SCOPE_LIMIT",
    "HONEST_SCOPE_LIMITS",
    "IsaBuildRecord",
    "KEY_BYTES",
    "LEAF_PREFIX",
    "MultiIsaParityReport",
    "NODE_PREFIX",
    "NONCE_BYTES",
    "REQUIRED_TARGETS",
    "RFC8439_SECTION_2_8_2_TAG_HEX",
    "TAG_BYTES",
    "aead_open",
    "aead_seal",
    "build_record_from_bytes",
    "chacha20_block",
    "chacha20_xor",
    "check_domain_separation",
    "consistency_proof",
    "inclusion_proof",
    "leaf_hash",
    "merkle_root",
    "node_hash",
    "open_envelope",
    "poly1305_mac",
    "seal_envelope",
    "sha256_hex",
    "verify_consistency",
    "verify_inclusion",
    "verify_multi_isa_parity",
]

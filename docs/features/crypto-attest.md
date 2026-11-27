# Cryptographic Attestation Primitives (`harness.crypto_attest`)

`harness/crypto_attest/` provides pure-Python standard-library verification primitives for deterministic multi-ISA build parity, RFC 6962 Merkle transparency proofs, and RFC 8439 ChaCha20-Poly1305 AEAD envelopes. Every check fails closed on missing inputs, malformed encodings, or single-bit tampering.

## Modules

- **`multi_isa_parity.py`**: Verifies deterministic build and execution digests across `x64-pe`, `x64-elf`, `rv64-elf`, `aarch64-elf`, and `wasm`. Rejects missing required targets, unknown or duplicate targets, non-zero exit codes, binary size overflows, single-ISA stdout divergence, and forged binary digests when raw bytes are supplied.
- **`merkle_attest.py`**: Implements RFC 6962 SHA-256 Merkle tree roots, inclusion proofs, and append-only consistency proofs with explicit domain separation (`0x00` leaf prefix, `0x01` internal node prefix). Rejects second-preimage node confusion and single-bit proof mutations using constant-time digest comparison.
- **`aead_envelope.py`**: Implements RFC 8439 ChaCha20-Poly1305 sealing, opening, and versioned JSON envelopes (`flywheel-aead-envelope/1`). Verifies the 16-byte Poly1305 authentication tag via `hmac.compare_digest` before decryption and matches the RFC 8439 Section 2.8.2 test vector tag (`1ae10b594f09e26a7e902ecbd0600691`).

## Usage

```python
from harness.crypto_attest import (
    aead_open,
    aead_seal,
    consistency_proof,
    inclusion_proof,
    merkle_root,
    verify_consistency,
    verify_inclusion,
    verify_multi_isa_parity,
)
```

## Honest Scope Limits

- **`multi_isa_parity.py`** verifies supplied build records and optional raw binary bytes; it does not execute target binaries or replace hardware ISA runners.
- **`merkle_attest.py`** verifies SHA-256 tree math and domain separation; it does not verify Signed Tree Head signatures or run log gossip protocols.
- **`aead_envelope.py`** is a pure-Python verification and attestation harness. Python big-integer arithmetic is not hardened against hardware timing side-channels; use vetted native cryptography for production secret custody.

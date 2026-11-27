# PQ KEM Attestation Gate

`harness/pq_kem_attest/` is a pure-stdlib MIT verifier for FIPS 203 ML-KEM-512 and X25519 hybrid post-quantum key exchange receipts across five target architectures: `x64-pe`, `x64-elf`, `rv64-elf`, `aarch64-elf`, and `wasm`.

## Checks Performed

The verifier locks the ring parameters to modulus `q = 3329`, degree `n = 256`, and rank `k = 2`. Any mismatch fails closed. Every polynomial entry is checked as a plain integer strictly inside `[0, 3328]`, rejecting booleans, floats, negative integers, and values at or above `3329`.

For the five-ISA binary inventory, the oracle confirms positive byte counts, valid 64-character hexadecimal `SHA-256` digests, a strict WASM size cap, and optional on-disk file hash verification. It also checks all four required Fujisaki-Okamoto and hybrid controls, `mlkem_ct_tamper`, `x25519_mitm`, `non_canonical_coeff`, and `aead_tag_tamper`, confirming every planted attack fails closed with `hybrid_committed == 0` across all five targets.

## Scope Limits

This module checks receipt structure, parameter bounds, artifact digests, and planted rejection controls. It does not substitute for a hardware side-channel audit of constant-time execution.

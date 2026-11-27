# ZK Pedersen and BuildOS-2.1 Cluster Attestation Gate

`harness/zk_pedersen_attest/` is a pure-stdlib MIT verifier for Slice 34 Curve25519 Pedersen zero-knowledge conservation receipts and Slice 35 Unified `BuildOS-2.1` distributed cluster receipts across five architectures: `x64-pe`, `x64-elf`, `rv64-elf`, `aarch64-elf`, and `wasm`.

## Checks Performed

For Slice 34 zero-knowledge proofs, the oracle enforces exact non-negative value conservation `v_in == v_out1 + v_out2`, confirms `verified == 1`, checks all commitment and Schnorr point hashes, and requires all four soundness controls to fail closed across every ISA.

For Slice 35 `BuildOS-2.1` clusters, the gate verifies four unified pillars, seven live twisted Edwards25519 equations, optional RFC 6962 `MTH(D[0:4])` cluster root reconstruction, five-ISA binary `SHA-256` invariants with optional on-disk checks, and all six cross-layer attack vectors failing closed across all five ISAs.

## Scope Limits

This module checks receipt structure, conservation equations, Merkle commitments, binary digests, and planted rejection controls. It does not execute elliptic-curve scalar multiplications directly.

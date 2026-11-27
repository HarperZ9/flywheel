# BFT Consensus Attestation Gate

`harness/bft_consensus_attest/` is a pure-stdlib MIT verifier for Slice 33 Zero-C five-ISA four-node Ed25519 Byzantine fault tolerant consensus and transparency log receipts.

## Checks Performed

The oracle enforces `3f + 1 = 4` validator nodes and a quorum of at least three distinct valid Ed25519 signatures on the committed block hash. Any equivocating double-vote at the same block height, duplicate vote, or invalid signature fails closed immediately.

When ordered log leaves are present, the verifier recomputes the RFC 6962 Merkle Tree Hash against the committed `ledger_root_hex`. It also checks all five target architecture binaries with valid 64-character `SHA-256` digests, optional on-disk hash checks, and all four Byzantine attack controls, `equivocation_double_vote`, `sub_quorum_2of4`, `forged_ed25519_sig`, and `tampered_parent_hash`, failing closed across all five ISAs.

## Scope Limits

This module checks receipt structure, quorum signatures, equivocation rules, Merkle commitments, binary digests, and planted rejection controls. It does not execute multi-machine asynchronous network consensus.

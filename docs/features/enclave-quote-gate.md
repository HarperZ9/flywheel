# Enclave Quote Gate

## Overview

`harness/enclave_quote_gate` audits Zero-C BuildOS Confidential Enclave Slice 28 records in pure Python stdlib under the OSI MIT license. Every bundle requires non-zero 64-hex `mr_enclave`, `enclave_root`, `quote_digest`, and Ed25519 signature point digests plus a 32-hex ChaCha20-Poly1305 AEAD tag across all five target ISAs: `x64-pe`, `x64-elf`, `rv64-elf`, `aarch64-elf`, and `wasm`.

## Freshness, Zero-Egress, and Fail-Closed Rules

Calling `verify_enclave_quote` or `verify_enclave_receipt_file` returns an immutable `EnclaveQuoteReport`. The report seals `enclave_quote_attestation_sha256`. It enforces strict monotonic nonce ordering, confirms `CAP_NET_EGRESS` stays denied under the zero-egress allowlist, checks cross-ISA digest parity, verifies attack-rejection floors across all five ISAs, and checks `engine-receipt/1` binary SHA-256 hashes, failing closed on stale nonce replay, egress bit violation, missing ISA, tampered binary hash, or `NaN`/`Inf`/`bool` latency ceiling.

## Scope Limits

This verifier inspects enclave quote fields, capability bitmasks, monotonic nonces, 5-ISA binary hashes, and receipt match flags in pure Python stdlib. It does not emulate CPU instructions or verify hardware SGX or TDX roots.

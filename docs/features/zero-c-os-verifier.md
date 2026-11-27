# Zero-C BuildOS Verifier

## Overview

`harness/zero_c_os_verifier` audits multi-ISA Zero-C BuildOS kernel slices from Slice 17 through Slice 24 in pure Python stdlib under the OSI MIT license. Every slice must carry all five architectures (`x64-pe`, `x64-elf`, `rv64-elf`, `aarch64-elf`, and `wasm`), a strict `zero_c=1` marker, positive binary sizes, valid 64-hex SHA-256 digests, and verified security attack rejection floors.

## Multi-ISA Attestation and Controls

Calling `verify_zero_c_os` or `verify_zero_c_os_tsv` returns an immutable `ZeroCOSReport`. The report seals `zero_c_os_attestation_sha256` over the sorted binary manifest. Helper functions validate ELF, PE, and WASM header magic bytes and extract 5-ISA records from `engine-receipt/1` envelopes, while any missing ISA, duplicate architecture, attack-rejection shortfall, forged catalogue ID, binary digest mismatch, or boolean or non-finite threshold fails closed.

## Scope Limits

This verifier checks multi-ISA slice completeness, binary magic and SHA-256 digests, attack counts, and caller-supplied receipt verdicts in pure Python stdlib. It does not emulate RV64 or AArch64 instructions or execute kernel binaries.

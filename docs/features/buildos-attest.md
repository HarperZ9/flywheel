# BuildOS Microkernel Triad Attestation (`harness.buildos_attest`)

`harness/buildos_attest/` verifies Zero-C BuildOS Slices 17 to 20 using only the Python standard library. It covers the signed boot RFC 6962 log root, the W^X capability scheduler trace, the zero-copy IPC Merkle VFS inode root, and the four cross-layer attack proofs that must fail closed to Slot A. Every numeric field must be a real integer, so `NaN`, `Inf`, floats, and booleans are rejected.

## Modules

`receipt_check.py` validates each `engine-receipt/1` envelope: schema, `MATCH` verdict, zero oracle exit, strict `sha256:` digests, full coverage of `x64-pe`, `x64-elf`, `rv64-elf`, `aarch64-elf`, and `wasm` binaries, and optional on-disk SHA-256 and byte parity with path containment.

`triad_reference.py` re-derives the Slice 20 reference values from first principles: the kernel image SHA-256, the RFC 6962 boot log root with `0x00` leaf and `0x01` node domain separation, the 9-tick scheduler trace SHA-256, and the 4-block VFS inode root.

`triad_gate.py` checks the Slice 20 oracle output. Each ISA must commit the clean triad (`status=1`, `epoch=20`, `ticks=9`, `vfs_blocks=4`) with roots that match the independent reference in constant time. Each ISA must also reject the epoch rollback (`-101`), W^X escalation (`-201`), IPC double send (`-301`), and VFS 1-bit corruption (`-401`) attacks with `triad_committed=0` and `fallback_slot=1`. The gate seals a deterministic `triad_attestation_sha256`.

## Usage

```python
from harness.buildos_attest import derive_triad_reference, verify_triad_oracle

report = verify_triad_oracle(oracle_output, reference=derive_triad_reference())
assert report.passed and report.attacks_rejected == 20
```

## Honest Scope Limits

These modules validate receipts, re-derive reference digests, and gate serialized oracle output. They do not compile, execute, or emulate BuildOS binaries, and they do not recompute receipt HMAC signatures.

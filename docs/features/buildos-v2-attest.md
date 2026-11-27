# BuildOS-2.0 Sovereign Attestation Gate

`harness/buildos_v2_attest/` is a pure-stdlib MIT verifier for Unified 12-Subsystem Zero-C `BuildOS-2.0` sovereign kernel receipts across five target architectures: `x64-pe`, `x64-elf`, `rv64-elf`, `aarch64-elf`, and `wasm`.

## Checks Performed

The oracle verifies all twelve ordered subsystem leaves and recomputes the RFC 6962 Merkle Tree Hash `MTH(D[0:12])` against the committed sovereign root. Any tampered leaf digest or missing subsystem fails closed immediately.

For the five-ISA binary inventory, the gate validates positive byte sizes, 64-character hexadecimal `SHA-256` digests, a WASM size ceiling, and optional on-disk file hash verification. It also audits all eight cross-subsystem attack controls, `bad_boot_sig`, `sv39_wx_violation`, `iommu_dma_escape`, `mlkem_ct_tamper`, `enclave_meas_mismatch`, `uncertified_gpu_shader`, `compositor_xwin_read`, and `hid_keylogger_tap`, requiring fail-closed rejection with `sovereign_committed == 0` across every ISA.

## Scope Limits

This gate validates receipt structure, Merkle commitments, binary digests, and planted attack rejections. It does not substitute for a bare-metal hardware audit of kernel execution.

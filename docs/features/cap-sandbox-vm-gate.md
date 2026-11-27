# Capability Sandbox VM Gate

`harness/cap_sandbox_vm_gate/` is a pure-stdlib MIT verifier for Slice 32 Zero-C five-ISA fuel-metered capability sandbox bytecode virtual machine receipts.

## Checks Performed

The oracle enforces positive fuel budgets within policy limits and checks `fuel_used <= fuel_budget`. Every recorded memory write must land in `[0, 31]` linear data memory, rejecting negative offsets, out-of-bounds indices, and writes to the read-only W^X code segment starting at address `1024`.

For hostcall isolation, the gate requires every permitted hostcall to satisfy `(cap_mask & required_cap) == required_cap` and rejects unauthorized capability escalation. It also checks all five target architecture binaries with valid 64-character `SHA-256` digests, optional on-disk hash checks, and all four sandbox-escape controls, `fuel_exhaustion`, `oob_linear_memory`, `wx_code_write`, and `unauthorized_hostcall`, failing closed across all five ISAs.

## Scope Limits

This module checks receipt structure, fuel bounds, memory write traces, capability masks, binary digests, and planted rejection controls. It does not execute guest bytecode programs directly.

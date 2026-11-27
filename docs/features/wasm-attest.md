# WebAssembly Binary Parser and Sandbox Gate (`harness.wasm_attest`)

`harness/wasm_attest/` provides pure-Python standard-library WebAssembly 1.0 binary parsing, import/export extraction, zero-egress sandbox policy enforcement, and manifest-backed bundle verification. Every check fails closed on malformed framing, forbidden host capabilities, size ceiling breaches, or single-bit SHA-256 tampering.

## Modules

- **`wasm_parser.py`**: Parses WebAssembly 1.0 binaries with zero external tools. Validates the `\x00asm\x01\x00\x00\x00` header, unsigned LEB128 section framing, canonical standard section ordering, and UTF-8 Import/Export tables.
- **`sandbox_policy.py`**: Enforces module byte ceilings (default `16,384` bytes), explicit host import allowlists, export presence, and fail-closed rejection of WASI (`wasi_snapshot_preview1`, `wasi_unstable`), filesystem, process, and network imports.
- **`bundle_gate.py`**: Audits a manifest-backed drop-in directory (`wasm_36pack_manifest.json`) for constant-time SHA-256 parity, declared byte sizes, MIT licensing, path containment, aggregate byte limits, and sandbox policy compliance, sealing a deterministic `attestation_sha256`.

## Usage

```python
from pathlib import Path
from harness.wasm_attest import verify_wasm_bundle

report = verify_wasm_bundle(Path("site-dropin-36pack"), max_total_bytes=204800)
assert report.passed
```

## Honest Scope Limits

- **`wasm_parser.py`** validates binary section framing and Import/Export tables; it does not type-check function bodies or execute bytecode.
- **`sandbox_policy.py`** enforces static import allowlists and size ceilings; it does not constrain host runtime glue code or execution fuel.
- **`bundle_gate.py`** verifies manifest and file integrity on disk; it does not execute modules in a browser or JavaScript engine.

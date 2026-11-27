# Remedy Receipts and Weight-Manifest Auditing

Two stdlib-only governance and owner-rights modules extend Flywheel's offline
verification surface:

- **`harness.remedy`**: machine-readable Check-Contest-Obtain-Remedy receipt
  protocol composing directly with `harness.contest` and `harness.merkle`.
- **`harness.weight_audit`**: local owner-rights binary and weight-manifest
  integrity scanner plus static outbound-socket and telemetry detector.

## Check-Contest-Obtain-Remedy (`harness.remedy`)

`adjudicate_contest` verifies four invariants fail-closed before issuing a
`flywheel.remedy-receipt/v1` record:

1. The contester's Ed25519 signature on `Contest` verifies against the
   contester's own public key (`FORGED_OR_UNSIGNED_CONTEST` on any forgery).
2. `contest.disputed_claim_sha256` equals `contested_output.claim_sha256`.
3. `output_bytes` and `audit_trace_bytes` hash to the exact SHA-256 digests
   recorded in `ContestedOutput` (`OUTPUT_HASH_MISMATCH` /
   `AUDIT_TRACE_HASH_MISMATCH`).
4. The deterministic re-derivation oracle emits a typed `RemedyVerdict`
   (`UPHELD`, `OVERTURNED`, or `REMEDY_ISSUED`) consistent with its
   `RemedyAction`.

`verify_remedy_receipt` and `verify_remedy_chain` re-verify individual receipts
and append-only prev-hash chains offline, committing the chain to an RFC 6962
Merkle root.

```python
from harness.remedy import (
    ContestedOutput, RemedyVerdict, adjudicate_contest,
    hash_bytes, verify_remedy_receipt,
)

co = ContestedOutput("out-1", hash_bytes(out_bytes), hash_bytes(trace_bytes))
receipt = adjudicate_contest(
    signed_contest, co,
    output_bytes=out_bytes, audit_trace_bytes=trace_bytes,
    oracle_fn=lambda o, t: (RemedyVerdict.REMEDY_ISSUED, corrected_bytes, "Mismatch fixed."),
    oracle_id="deterministic-rerun-v1",
)
ok, verdict = verify_remedy_receipt(receipt, output_bytes=out_bytes, audit_trace_bytes=trace_bytes)
assert ok and verdict == "MATCH"
```

## Owner-Rights Weight and Binary Integrity (`harness.weight_audit`)

`build_weight_manifest` walks a local model or container directory, computes
SHA-256 digests and byte lengths for every weight blob and native binary
(`.safetensors`, `.gguf`, `.bin`, `.pt`, `.pth`, `.onnx`, `.so`, `.dll`,
`.dylib`, `.exe`, `.wasm`), and seals them with an RFC 6962 Merkle root.

`audit_artifact_root` checks the directory offline and fails closed on:

- Unhashed weight or binary blobs (`UNHASHED_WEIGHT_OR_BINARY`),
- Missing manifest files (`MISSING_MANIFEST_FILE`),
- One-byte or larger weight/binary mutations (`TAMPERED_WEIGHT_OR_BINARY`),
- Edited manifests (`MANIFEST_MERKLE_TAMPER`),
- Unauthorized Python AST or shell outbound sockets outside loopback and the
  operator's explicit `allow_hosts` list (`UNAUTHORIZED_OUTBOUND_SOCKET`),
- Undocumented telemetry SDK imports (`UNDOCUMENTED_TELEMETRY`) or
  locked-firmware/audit-bypass flags (`LOCKED_FIRMWARE_OR_AUDIT_BYPASS`).

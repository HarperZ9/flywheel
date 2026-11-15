# Spec findings from the cross-language receipt port (wave 2)

- Date: 2026-07-02
- Source: porting the portable witness receipt (SPEC section 17) from the Python
  reference (`emet/witness_receipt.py`) to the Rust (`impl/rust/emet.rs`) and
  Node.js (`impl/js/emet.js`) implementations.
- Purpose: same as the other findings docs -- "where your implementation and the
  spec disagree, fix the spec." Porting a cross-implementation feature is a
  differential oracle: any field whose value is per-implementation but sits inside
  the cross-implementation content address will silently break byte-identical
  re-derivation. Exactly one did.

## F1 -- The `witness` block must not govern the content address (RESOLVED -- real divergence)

**Severity: high (re-derivability).** SPEC section 17.2 promised that "the SAME
subject bytes, the SAME `spec_version`, the SAME `corpus_version`, and the SAME
`issued_at` yield a byte-identical `receipt_id`" and that "the address is
byte-identical across conforming implementations." But the reference computed
`receipt_id` over the whole receipt minus only `receipt_id` and `signature` --
which INCLUDED the `witness` block. The `witness` block carries
`implementation` (a per-impl name like `emet-python-reference` vs
`emet-rust-reference`) and `self_sha256` (that implementation's OWN
artifact-of-record hash, SPEC section 14). Both are intrinsically
per-implementation.

Consequence: the same subject/verdict/spec/issued_at produced a DIFFERENT
`receipt_id` in Python vs Rust vs Node.js, directly contradicting the section
17.2 guarantee. The single-implementation Python tests could not catch this
(one impl, one witness), so it only surfaced when a second implementation
emitted a receipt from the same envelope.

**Resolution.** The content address now excludes `receipt_id`, `signature`, AND
`witness`: `receipt_id = sha256(canonical(receipt minus those three))`. The
`witness` block still travels in the receipt as descriptive metadata (a verifier
may read it to learn who produced the receipt) but does not govern the address.
This is faithful to the guarantee as written, which enumerates subject bytes +
`spec_version` + `corpus_version` + `issued_at` -- the producer identity was
never in that list. SPEC section 17.2 updated; the Python reference, the Rust
port, and the Node.js port all now emit a byte-identical `receipt_id` for the
same input (verified 3-way), and a receipt produced by one re-verifies unchanged
under the others.

## F2 -- Rust has no std HMAC, but HMAC-SHA256 composes cleanly over SHA-256 (RESOLVED -- design note)

**Severity: none (optional feature).** SPEC section 17.4 makes the signature
OPTIONAL and out-of-spec; the design allowed the Rust port to fall back to
`signature: null` since Rust's standard library has no HMAC and the impl forbids
external crates. In practice HMAC-SHA256 (RFC 2104) composes in ~15 lines over
the existing hand-rolled SHA-256 primitive, so the Rust port implements it fully
and verifies signed receipts as well as unsigned ones. The hand-rolled HMAC is
pinned to RFC 4231 test vector 2 and produces byte-identical signatures to the
Python `hmac` module and Node's `crypto.createHmac`, so a receipt signed by any
one implementation verifies under the others. No spec change; recording the
choice so the null-fallback path is understood as a floor, not the ceiling.

## Note on the Go implementation

`receipt`/`check` are NOT yet ported to the Go implementation (`impl/go/emet.go`).
Its 5 receipt conformance vectors are skipped by capability
(`EMET_SKIP_CAPABILITIES=receipt`); Go passes the 35 core vectors. Porting
`receipt`/`check` to Go is the remaining parity item.

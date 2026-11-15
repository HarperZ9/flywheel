# EMET -- Rust second implementation

A clean-room second implementation of the EMET core, written against SPEC.md and
conformance/vectors.json ONLY, in pure Rust with no external crates (hand-rolled
SHA-256). Purpose: a second, INDEPENDENT codebase that passes the same conformance
vectors -- which is what converts re-derivability from asserted to demonstrated
(SPEC section 12).

## Build and test

  rustc -O emet.rs -o emet
  python ../../conformance/run.py ./emet
  ( cd . && cargo test --release )   # 13 receipt behavior tests

Expected: CONFORMANCE 40/40 vectors pass.

## Receipt support (SPEC s.17)

This impl implements `emet receipt --from-json <file|->` and `emet check
<receipt.json> [--recompute-from-paths]`. The content address (`receipt_id`) is
byte-identical to the Python and Node.js receipts for the same
subject/verdict/spec/issued_at. HMAC-SHA256 signatures are composed over the
hand-rolled SHA-256 primitive (no external crate) and pinned to RFC 4231 test
vector 2, so this implementation verifies signed receipts as well as unsigned ones.

## Status

Compiled and passing all 40 conformance vectors (rustc, `-O`) plus 13 inline
receipt tests (`cargo test`). The hand-rolled SHA-256 was verified against a
reference on known vectors before transcription, and the hand-rolled canonical
JSON reproduces the Python `--json` envelope byte-for-byte on the governed fields.
This cross-LANGUAGE impl proves the spec is implementable; it does NOT by itself
convert re-derivability from asserted to demonstrated -- it shares the operator
with the other three. For the STRONGEST claim, a truly different-AUTHOR
implementation from the spec alone is still the open, load-bearing deliverable
(SPEC section 12).

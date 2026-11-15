# EMET -- Node.js third implementation

A clean-room third implementation of the EMET core, written against SPEC.md
ONLY, in plain Node.js using built-in modules only (no npm, no dependencies).
Purpose: another codebase, in a different language, that passes the same
conformance vectors -- strengthening the claim that the spec is implementable
from its text alone. It does NOT by itself convert re-derivability from asserted
to demonstrated: SPEC section 12 requires a DIFFERENT-author implementation, and
this one shares the operator. See Status.

## Build and test

  python conformance/run.py impl/js/emet.js
  node --test impl/js/test_receipt.js        # 13 receipt behavior tests

(Run from the repository root.) Expected: CONFORMANCE 40/40 vectors pass.

## Receipt support (SPEC s.17)

This impl implements `emet receipt --from-json <file|->` and `emet check
<receipt.json> [--recompute-from-paths]`. The content address (`receipt_id`) is
byte-identical to the Python and Rust receipts for the same
subject/verdict/spec/issued_at (the per-implementation `witness` block is excluded
from the address, s.17.2). HMAC-SHA256 signatures use the built-in
`crypto.createHmac`; an unsigned receipt verifies on the content address alone.

## What this implementation surfaced

Writing this from the spec alone exposed a detail the existing vectors did not
catch: the marker count's semantics (occurrence vs distinct-entry). The reference
counts NON-OVERLAPPING OCCURRENCES, so a repeated marker counts each time; SPEC
did not say so, and the four refuse vectors did not discriminate. SPEC section 16
now pins the scan, and a new vector (`refuse-repeated-marker-occurrence-count`)
locks it. That divergence -- not the passing run -- was the most valuable output
(CONTRIBUTING: "where your implementation and the spec disagree, fix the spec").

## Status

Honest caveat: this is a SAME-AUTHOR / same-operator implementation. Like the
Rust impl, it shows the spec is implementable -- a second language reproducing
the pinned verdicts and exit codes from SPEC.md alone -- but it does NOT yet
clear the SPEC section 12 bar. That section is explicit: re-derivability is
DEMONSTRATED only by an INDEPENDENT second implementation, and "internal
consistency" is all that a same-party impl against the same vectors can show.
The cross-LANGUAGE coverage strengthens the "the spec is implementable" claim;
making it airtight still requires a truly different-AUTHOR implementation
written from the spec alone. Until that exists, no party should treat
re-derivability as proven.

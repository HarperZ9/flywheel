# Forum Feedback Reply Draft

Date: 2026-07-09

## Reply

You are asking the right question. The honest answer is: functional deep verification is implemented and covered, but I do not yet have a dedicated scaling benchmark published for `verify(deep=True)`.

The shape should be straightforward to measure. `verify()` is entry-count bound: it walks the hash chain, checks sequence/prev links, and recomputes each entry hash. `verify(deep=True)` adds payload work: for every content-addressed body still present, it re-hashes the body and compares it to the stored payload hash. If a body has been redacted down to hash-only, deep verification skips that absent body while the chain still verifies.

So the expected cost curve is roughly:

- shallow verify: `O(entries)`;
- deep verify: `O(entries + present payload bytes)`;
- cold file-backed verify: reload cost plus the same verification cost.

The benchmark I want to add next is a matrix over entry count, payload size, redaction ratio, storage mode, and warm vs cold reload. It should publish wall time, entries/sec, present payload MB/sec, ledger size, payload size, and negative controls for tampered payloads. That would answer whether deep verification becomes the first scaling bottleneck and where the breakpoints are.

Your read is right: content addressing gives a clean immutability/redaction trade-off, but it also makes deep verification a measurable systems problem. That benchmark should be first-class, not hand-waved.


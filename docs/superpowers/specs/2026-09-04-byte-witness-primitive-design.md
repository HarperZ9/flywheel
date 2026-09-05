# Byte witness: sealing exact bytes into an offline-checkable chain

Retrospective design note. 2026-09-04.

Status: shipped. Code at `harness/byte_witness.py` and
`harness/byte_witness_verify.py`, committed as `d30edf8` (the primitive) and
`efff7c0` (the chain-not-a-MATCH correctness rule and the tests). Tests at
`tests/test_byte_witness.py` and `tests/test_byte_witness_verify.py`, 96 cases
green (30 and 66, counted by pytest collection on 2026-09-04; the file holds
54 test functions and parametrization supplies the rest).

This note is written after the fact. It records what the primitive is, the
decisions that shaped it, and the places where the shipped design differs from
the proposal that preceded it. It is a retrospective, not a plan.

## What it is

Every other sealing path in this repository seals a structure: a tool-call
receipt, a verdict, a stage record. A byte witness seals the bytes themselves.
It records the sha256 of a byte sequence, how many bytes there were, and the
link to the record before it in a chain. It never carries the bytes. The caller
keeps those wherever they live and hands them back to the verifier when a check
is asked for.

This is the one thing a verification pipeline in any domain needs and cannot get
from a typed receipt. The instrument frame that came off a device. The Lean file
a kernel accepted. The statute text a citation points into. The exact prompt
bytes a model was handed. A record over material nobody may republish is still a
record somebody can check, because the record travels where the content may not.

## Two files, two disciplines

The seal side and the check side are separate files on purpose, and they hold
opposite contracts.

`byte_witness.py` seals, and it refuses loudly. A witness that cannot be taken
honestly raises `WitnessError`. Text handed in where bytes belong raises, rather
than picking an encoding and silently deciding what the bytes were. A span cited
over a different byte string raises. A context value outside the JSON data model
raises at sealing time, not at some later read.

`byte_witness_verify.py` checks, and it never raises. It imports nothing outside
the standard library and this repository, it needs no network, and hostile input
comes back as a named verdict. A verifier that crashes on a malformed record
tells the stranger running it nothing about the record. The stdlib-only
constraint is what lets the check side run in a place that trusts none of the
seal side's dependencies.

## Three verdicts, and the third is not the second

The verify side answers in three words, and they are not interchangeable.

- `MATCH`: every check that was asked for ran and reproduced.
- `TAMPERED`: a check ran and the record does not hold.
- `UNVERIFIABLE`: nothing could be checked. A malformed record, or bytes nobody
  could produce.

Reading the third as the second turns an archive nobody can reach into an
accusation. Reading it as the first turns it into a lie. So `UNVERIFIABLE` is its
own answer, carried by its own failure classes (`BYTES_UNAVAILABLE`,
`MALFORMED`, `NO_SIGNER`) rather than folded into either neighbor.

One case looks like it should need bytes and does not. A span that runs past the
length the record itself claims is a contradiction inside the record. That is
`TAMPERED` on the record alone, with no bytes in hand, because the record refutes
itself.

## The decisions that shaped it

**A link folds in prev.** A record's link is the canonical sha256 of the whole
record, and the record includes `prev`. So the same bytes witnessed twice in one
chain produce two different links, and a replayed record is not a valid
continuation of the chain it is replayed into. Order and position are part of
what the link commits to, not just content.

**A chain with a resolver that misses one record is not a MATCH.** This is the
correctness rule that `efff7c0` is named for. When a caller passes a resolver,
they are asking for the bytes to be checked. If the archive cannot produce the
bytes for even one record, `MATCH` would claim every byte sequence reproduced,
which is false. The chain is linked but not fully reproduced, so the verdict is
`UNVERIFIABLE` with `BYTES_UNAVAILABLE`, and the detail says how many records
went unresolved. A resolver that throws is treated the same as one that returns
nothing: the caller's storage being offline is not the verifier's failure mode.

**A lifted segment defaults to UNVERIFIABLE, not MATCH.** `verify_chain` takes a
`start` argument for what the first record must point back at, defaulting to
genesis. A segment cut out of a longer chain, verified on its own, reports a
broken link rather than quietly matching. A caller who holds the earlier head
passes it as `start` and the segment checks against it.

**Spans bind a claim to a place.** `cite()` seals one byte range and carries its
own digest, so a record can say not just what the bytes were but which range
inside them a claim points at. The sentence a citation quotes, the field inside
an instrument frame, the theorem statement inside a source file. `witness_file`
does not offer spans, because citing a range means reading it, and a caller who
has read the range can witness those bytes directly.

**does_not_prove is never empty.** It states what a witness leaves open, and it
takes `signed` and `anchored` flags that change the wording rather than removing
lines. An unsigned chain says anyone who can rewrite a record can recompute every
link after it. A chain with no external anchor says `observed_at` is what the
caller wrote down and no clock here checked it. The honest nulls stay whatever
the arguments say.

**Signatures are checked on stdlib alone.** `verify_signature` verifies an
Ed25519 signature over a record's link, using the repository's pure-Python
`ed25519_verify`. The signed message is the link as its lowercase hex text.
Nothing on the verify side ever holds a key. Signing happens wherever the key
lives.

## Where the shipped design differs from the proposal

The design that preceded this shipped with real changes. Recording them keeps the
retrospective honest.

- The proposal called the byte-range primitive a citation. The shipped name is
  `Span`, with `cite()` as the verb that seals one. Span reads as a place inside
  bytes. Citation carried a claim about correctness the primitive does not make.
- The proposal had a flat `does_not_prove` list. The shipped one is
  parameterized by `signed` and `anchored`, so the honest nulls track what the
  caller actually has instead of listing every caveat unconditionally.
- `witness_file` was not in the proposal. It seals a file's bytes with a chunked
  streaming hash and never holds the whole payload in memory, which the tests
  exercise past the one-chunk boundary.
- The proposal sealed a digest into the record body. The shipped link is the
  canonical hash of the record computed on demand, which reuses the repository's
  existing `canonical_sha256` and keeps the record itself free of a
  self-referential field.
- The seal side reuses `_digest_well_formed` and `_sha256_hex` from
  `tool_call_receipt`, and the verify side imports `MATCH`, `TAMPERED`, and
  `UNVERIFIABLE` from the same place. The verdict words are one vocabulary across
  the receipt family, not a second set coined here.

## Canonicalization

The record canonicalizes with sorted keys through `evidence_json`, so no reader
needs to know a field order. This is the sort-keys path, the same one
`evidence_json` uses for its own canonical bytes. It is deliberately not the
fixed-field-order path that `tool_call_receipt` and `model_receipts` use for
byte parity with a Rust twin, because the byte witness has no Rust twin to match.
A future Rust verifier would pin the field order and re-derive a golden fixture,
the way the model-boundary receipt already does.

## What the tests hold

The two suites are the specification the code is measured against.

The seal suite holds that a record carries the digest and the count and nothing
else, that the bytes never appear in the record, that text and non-bytes and
empty labels and malformed prevs are refused, that a span cited over other bytes
is caught at sealing time, that the link folds in prev so a replay is not a
continuation, and that `witness_file` agrees with `witness_bytes` including past
the streaming boundary.

The verify suite holds the three verdicts by name, never merely as not-MATCH. It
covers tampered digests and lengths and spans, the span-past-length
self-contradiction with no bytes, hostile input across the JSON value space
returning a verdict and never a raise, the whole-chain resolver path, a removed
middle record, an edited record breaking every link after it, a lifted segment
with and without its earlier head, the one-unresolved-record rule that
`efff7c0` exists for, a resolver that throws, and a real Ed25519 signature
verifying over the link with a relabelled record failing.

## What it does not establish

A digest says the bytes did not change after they were witnessed. It says nothing
about whether they were true, or correct, or complete. A chain proves the order
and integrity of the records it holds, and it cannot show that a record was never
written, so an omitted step leaves no broken link behind. A span proves a range
hashes to what was recorded, not that the range is the right one for the claim it
was cited for. Without a signature, anyone who can rewrite a record can recompute
every link after it. Without an external anchor, no clock here dates the chain.

These are the primitive's boundaries, and `does_not_prove` states them at
runtime so a caller reading a verdict reads the limits with it.

## What was built on top of it after this note

This note describes the primitive alone. The work that followed it wraps the
primitive around the agent loop so every tool call witnesses both sides,
budgets the chain for transport, re-derives every link on the desktop client
rather than trusting a gateway verdict, and pins the two canonical encoders
against each other so a Python change cannot silently break the Dart read.
That layer, its honest nulls, and what a regulated domain actually gets from
it are written up in
`project-docs/architecture/BYTE-WITNESS-2026-09-04.md`. Read this note for why
the primitive is shaped the way it is; read that one for what it does in the
product.

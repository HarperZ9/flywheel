# The byte witness

Status: shipped. Last verified 2026-09-04 against the code cited below.
Why the primitive underneath is shaped the way it is, including the
alternatives that were rejected:
`docs/superpowers/specs/2026-09-04-byte-witness-primitive-design.md`.

Flywheel sells verification into fields where a wrong answer costs something:
clinical, legal, financial, scientific, engineering. Those fields do not ask
whether a model is clever. They ask what was done, in what order, over which
exact bytes, and whether a stranger can check that later without trusting the
party who produced it. Answering that question is the product.

## The claim, and its limit

The byte witness answers one narrow question. It says whether a given sequence
of bytes is the sequence observed at a named moment, and whether the record of
that observation sits in an unbroken order with the records around it.

It does not say the bytes were correct, complete, or authorized. Every verdict
carries a `does_not_prove` list, and the list is never empty regardless of what
the arguments claim (`harness/byte_witness.py:191`,
`harness/action_witness.py:195`). A tool that overstates once in a regulated
setting is finished, so the overstatement is made structurally hard rather than
left to whoever writes the copy.

## Three verdicts

`MATCH`, `TAMPERED`, `UNVERIFIABLE`. The failure classes are named in one
vocabulary on both sides of the wire: `MALFORMED`, `DIGEST_MISMATCH`,
`LENGTH_MISMATCH`, `SPAN_OUT_OF_RANGE`, `SPAN_MISMATCH`, `LINK_BROKEN`,
`BYTES_UNAVAILABLE`, `SIGNATURE_INVALID`, `NO_SIGNER`
(`harness/byte_witness_verify.py:33`).

`UNVERIFIABLE` is the load-bearing one. Records travel and raw bytes usually do
not, so the ordinary honest answer for a chain that arrived without its data is
`UNVERIFIABLE` with the links intact. Reading that as `TAMPERED` turns an
archive nobody can reach into an accusation. Reading it as `MATCH` turns it
into a lie. Both readings are cheap, and both are disqualifying, which is why
the distinction is enforced in the verifier, asserted in the tests, and
rendered in those words on screen.

Nothing in the verify path raises. Hostile input becomes a named verdict,
because a verifier that crashes on a bad record has told its caller nothing
about the record.

## What the primitive is

Four properties, each a line of code rather than a policy.

**Content-addressed.** A record identifies its bytes by SHA-256, never by
location, filename, or the assertion of whoever handed it over. Files stream in
1 MiB chunks (`harness/byte_witness.py:31`), so witnessing a large artifact
never loads it.

**The record does not grow with what it witnesses.** A record holds a digest, a
length, an optional list of cited byte ranges, and a small context map. A
witness over 10 MB is the same size as a witness over 11 bytes. This is what
makes witnessing every action affordable at all. A two-record pair for a small
tool call measures 647 canonical bytes, 323 per record (measured 2026-09-04 on
the `list_dir` shape, high confidence), and that figure moves with label and
context length rather than with payload size.

**Chain-linked.** Each record's `prev` is the canonical SHA-256 of the record
before it, which itself folds in that record's own `prev`. Rewrite any record
and every link after it breaks. The chain proves order and integrity for the
records it holds. It cannot show that a record was never written, so an omitted
step leaves no broken link behind, and that limit is stated in the
`does_not_prove` list rather than papered over.

**Verifiable on stdlib alone.** `harness/byte_witness_verify.py` imports
nothing outside the standard library. A regulator, an auditor, or a customer's
own engineer rechecks a chain without installing Flywheel, without network
access, and without a key.

## Cited ranges

`cite(data, start, end, note)` binds a byte range to a claim, so a citation can
show that a quoted span came from the document at those offsets. A span whose
range does not fit the length its record claims verifies as `TAMPERED` with no
bytes supplied at all, because the record refutes itself
(`harness/byte_witness_verify.py:131`). What a span cannot do is show that the
range is the right one for the claim it was cited for. That line is in the
`does_not_prove` list too.

## Native to every action

`harness/action_witness.py` wraps the primitive around the tool loop. Every
tool call witnesses both sides, the arguments going in and the result coming
back, linked into one chain per run.

Three properties make it native rather than opt-in.

The writer never raises. A full disk or a read-only directory counts a dropped
record and prints why, and the run continues (`harness/action_witness.py:96`).
Verification that can break the work gets switched off, and a witness that is
off witnesses nothing. Note the asymmetry a dropped write creates: the record
stays in the in-memory chain, so the chain the run hands back is whole while
the log on disk reads as broken. The stderr line says so at the moment it
happens.

`open_chain` returns `None` instead of raising when a chain cannot be opened
(`harness/tool_witness.py:34`).

The chain leaves the process whether or not receipts are being written to disk.
A receipt directory is opt-in. The chain is what the run did, so a caller who
never asked for files still gets the records (`harness/router_agent.py:129`).

## The transport bound

A run result carries its records so the caller can recheck offline. The gateway
refuses a result over `MAX_RESULT_BYTES = 250_000`
(`harness/gateway_operation_process.py:14`) and bounds a run at twelve steps
(`harness/gateway_operation_shape.py:65`), roughly 24 records, well inside the
cap. Direct callers have no step bound, so the budget is stated where the block
is built: `WITNESS_RECORD_BUDGET = 64_000`.

Over budget, the chain is omitted whole and the block says so in words. It is
never trimmed. A chain missing its middle verifies as `TAMPERED`, which would
accuse a run of something the transport did. The count and the head still
describe the whole chain, and the records remain on disk in the run's
`action-witness.jsonl`.

## The surface re-derives

The desktop client does not render a verdict the gateway computed. It
recomputes every link in Dart (`desktop/lib/models/byte_witness.dart`,
`byte_witness_chain.dart`, `canonical_json.dart`), so a compromised gateway, or
merely a wrong one, cannot make the screen say `MATCH`.

That only holds if the two canonical encoders agree byte for byte, and nothing
in a Dart test would notice the Python side moving underneath it. So the
vectors are produced by the engine and pinned: `tests/test_byte_witness_surface.py`
reads the Dart test file and fails when the copies drift. A companion check in
`tests/test_run_action_witness.py` reads the Dart parser and fails when the
engine renames a key the surface looks for. Without it, that rename would leave
an intact run reading as unparseable on screen, with nothing failing in between
to say so.

Two places render it. `desktop/lib/widgets/action_witness_line.dart` shows a
finished run's own chain in the live tail, checked from the result already in
hand. `desktop/lib/widgets/action_witness_panel.dart` takes a chain from
anywhere, including one exported months ago from a machine that no longer
exists.

Across the two, four states are named and none is silence: a checked
chain, a chain too large to travel, a result that carried no chain, and
text that does not read as records. A parse failure is reported as a parse
failure, never as a verdict about anyone's bytes.

## Honest nulls

**Nothing in the live path signs a witness record.** `verify_signature` exists
(`harness/byte_witness_verify.py:230`, Ed25519 over the record's link, stdlib
verify) and returns `NO_SIGNER` when there is no signature, which is every run
today. Unsigned means anyone who can rewrite a record can recompute every link
after it and leave the chain reading as intact. That sentence ships in the
`does_not_prove` list with every verdict.

**No clock is checked.** `observed_at` is what the caller wrote down. Dating a
chain takes an external anchor, and the run path anchors nothing.

**The engine omits the witness key for a run that took no witnessed action and
for a run that predates the chain alike.** The surface does not guess which,
and says only that no chain was handed over.

## What a domain gets

The primitive is domain-free on purpose. It takes bytes and returns a record,
so a field adds an oracle and a citation convention instead of a new integrity
layer.

- Clinical: which exact version of a protocol document a recommendation was
  read from, and which paragraph range.
- Legal: that a quoted clause sits at those offsets in that filing, and that
  the retrieval order was not rearranged afterward.
- Financial: that the figures a model summarized are the figures in the filing
  as received.
- Scientific: that the instrument output feeding an analysis is the output the
  instrument produced, with the analysis steps in recorded order.

None of those is a claim that the recommendation, the reading, the summary, or
the analysis is correct. Correctness belongs to the oracle, and the oracle
needs this underneath it to be worth running twice.

## Files

| Concern | File |
| --- | --- |
| The primitive | `harness/byte_witness.py` |
| The verifier | `harness/byte_witness_verify.py` |
| Per-action wrapping | `harness/action_witness.py`, `harness/tool_witness.py` |
| Run emission and budget | `harness/router_agent.py`, `harness/local_tools.py` |
| On-device re-derivation | `desktop/lib/models/byte_witness*.dart` |
| On-screen verdicts | `desktop/lib/widgets/action_witness_line.dart`, `action_witness_panel.dart` |
| Cross-language gates | `tests/test_byte_witness_surface.py`, `tests/test_run_action_witness.py` |

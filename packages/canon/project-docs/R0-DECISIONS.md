# R0 — decisions of record

The decisions that frame the block round-trip go/no-go gate, continuing the log
in F0-DECISIONS.md and F1-DECISIONS.md and recorded in the same shape the
`adr-decision` kind captures. Each is accepted unless marked otherwise.

R0 is the first band that turns a record into bytes and reads it back. It ships
three layers under one gate:

- `src/canon/region.py` — the byte boundary. `extract_region` / `splice_region`
  partition a managed file into `prefix + inner + suffix` with a byte-exact
  identity, and only `inner` is canon's to rewrite.
- `src/canon/textblock.py` — the record-to-text layer. `render_region` projects
  a scope-homogeneous block set into the region interior; `ingest_region` reads
  records back out and speaks the same grammar.
- `src/canon/fidelity.py` — the go/no-go artifact. `roundtrip_report` renders,
  ingests, and returns a `FidelityVerdict`: did the set round-trip to its
  canonical form, is the render a fixed point, are the outside bytes preserved
  across the host encoding matrix, and is every dropped field an accounted-for
  declared drop.

## D-12 — One LF line model; a bare CR is illegal on both legs
**Status:** accepted (this build, 2026-08-28).
**Context:** Managed files arrive from every host: a CRLF Windows checkout, an LF
Unix checkout, a file with a leading BOM. A block body can itself contain a bare
`\r`. The line model has to be one thing, or render and ingest can disagree on
where a line ends and a buried CR can splice the next sentinel onto a body line.
**Decision:** Normalize `CRLF -> LF` only, then split on `\n`. A bare `\r` that
survives normalization is illegal: render refuses to emit one, ingest refuses a
residual one. The host terminator is the only CR ever normalized, and it is not
content, so there is no `CR -> LF` content drop to declare.
**Consequence:** the "a buried CR joins the next sentinel into a body line"
injection the design flagged is closed on both ends. The declared-drop ledger
carries no line-ending drop, because none is lost.

## D-13 — render's refusal set is a strict superset of ingest's constraints
**Status:** accepted (this build).
**Context:** Two grammars face each other. render emits sentinel-delimited
blocks; ingest parses them back with a regex that already excludes `"`, `<`, `>`,
and `\n` from an id or sup. If render can emit a record that ingest then rejects,
the round-trip fails on a record render itself produced, and the failure surfaces
at the wrong leg.
**Decision:** render refuses, up front, any record it cannot represent, so every
record render emits re-ingests. render owns the refusals for a non-dict data, a
missing provenance, a non-int or negative create_ord, a duplicate id, and an
empty, CR-bearing, or marker-bearing id or sup. ingest additionally refuses a
sentinel whose token carries a marker (its regex excludes `<` and `>`), which is
strictly inside render's set.
**Consequence:** a refusal is attributable to the leg that owns it. render never
emits text the ingest leg would reject, so a round-trip no-go is a real fidelity
failure, not a grammar mismatch between the two halves.

## D-14 — the go/no-go never propagates an exception
**Status:** accepted (this build; hardened under the R0 audit, see D-16).
**Context:** `roundtrip_report` is the gate a later renderer calls before it
writes a file. If the gate can raise, a bad record is an unhandled traceback out
of the verification layer instead of a recorded no-go, and the write path has to
guess whether an exception means "unsafe" or "bug in the gate".
**Decision:** every refusal on every leg (render, extract, ingest) is caught and
returned as a `Refusal` with `ok=False`. The verdict is the single, total answer;
the gate is a function from any input to a verdict, never a throw.
**Consequence:** a caller reads one boolean and a refusal list. No input, however
malformed, escapes the gate as an exception. This is the contract the audit put
under adversarial pressure.

## D-15 — the drop ledger diffs against the raw input, not its own reference
**Status:** accepted (this build).
**Context:** The text leg drops foreign-provenance fields and `temporal.valid_until`
by design. Something has to certify that everything else survived. The tempting
shortcut is to diff the round-tripped record against `canonicalize_record`, the
function that computes what ingest should produce.
**Decision:** `classify_losses` diffs the round-tripped record against the RAW
input, never against `canonicalize_record`. It enumerates every field with
`dataclasses.fields` over Provenance and Temporal, so a field added to the schema
cannot slip the ledger unlisted. A changed field outside the declared-drop
vocabulary is an UNDECLARED loss and fails the gate closed. The vocabulary
reconciles against the backend capability tokens (`CAP_FOREIGN_PROVENANCE`,
`CAP_TEMPORAL`), and a zero-drop SqliteBackend witnesses in the tests that the
raw input is itself faithfully storable.
**Consequence:** the renderer and its own reference can never agree on a mistake
and pass. The "before" the ledger trusts is grounded in a store that loses
nothing, not assumed.

## D-16 — a type-constructible record is a valid input; the gate owns its refusal
**Status:** accepted (this build, 2026-08-28; audit-driven).
**Context:** `Record` and `Provenance` are frozen slots dataclasses with no
`__post_init__` and no annotation enforcement, and `Record.from_dict` deep-copies
whatever `data` holds. So a type-invalid record is constructible: `data=None`
reaches a record from a deserialized export, `provenance=None` from a partial
store, a string or float `create_ord` from a loose source. An adversarial audit
(five finder lenses over the R0 surface) confirmed five defects and refuted one.
All five shared one root: the render leg dereferenced a field before guarding its
type, so the gate raised instead of returning a no-go, and in two cases ingest
owned a refusal render should own, breaking D-13.
**Decision:** any type-constructible `Record` is a legal input to the gate, and
the gate refuses it on the render leg rather than raising or deferring to ingest.
render guards non-dict data, a missing provenance, and a non-int or bool
create_ord before touching them; `_check_token` rejects an empty or CR-bearing
id or sup, moving those refusals onto the render leg where D-13 requires them.
The fix was driven test-first, eighteen tests watched red before green.
**Consequence:** `roundtrip_report` returns `ok=False` with a render `Refusal`
for every constructible record and never propagates an exception, closing the gap
D-14 promised. The refuted finding (a CR in an id caught fail-closed through the
ledger lens) needed no separate fix, because the same render-leg guard now owns
that refusal too.

## The audit, recorded
The R0 gate landed on this branch (commit `R0: block round-trip fidelity gate`),
then an adversarial audit ran against it before the branch was proposed for
merge. Result: six candidate findings checked, five confirmed, one refuted. The
five confirmed collapsed into the single root above and were folded in TDD-style
in the following commit. The go/no-go artifact was re-run on a realistic
multi-scope corpus (a workspace region of three blocks with a supersedes link and
multiline bodies, a global region of two blocks, against a real host file):
both scopes returned GO, zero undeclared losses, zero refusals, idempotent,
outside bytes preserved. R0's GO is adversarially witnessed, not only
self-tested.

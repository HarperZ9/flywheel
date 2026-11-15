# RATIONALE - why EMET is shaped the way it is

> **Companion to [SPEC.md](SPEC.md).** SPEC.md says *what* EMET does and *what it
> must never do*. This document says *why those constraints are forced* - and it
> derives the answer from first principles, so you can check it without taking
> anyone's word for it.

## A note on how to read this

This is a **derivation, not a warrant.** Nothing here asks you to accept a claim
because a thesis, a corpus, or an author asserts it. Every section earns its
conclusion by an argument you can re-run, and every conclusion names a
**refuter** - the concrete observation that would break it. If a section ever
reduces to "because the corpus says so," that is a defect in the section, not a
load-bearing premise; report it.

The supporting research under `research/` is **further reading, never warrant.**
You may consult it to see the longer form of an argument or to trace its
intellectual lineage, but no claim in this document stands *because* `research/`
says it. The claims stand because they re-derive - or they fall.

This discipline is not decoration; it is **EMET's own thesis applied to its own
documentation.** EMET's entire reason for existing is the principle that trust
must come from re-derivation, not from authority asserted in-band. A rationale
that justified EMET's no-authority design *by appeal to authority* would commit
the exact error EMET's `refuse` command strips out of a file - a system vouching
for itself in-band. So this document is held to **SPEC §6 Boundary 1 - facts,
not authority - applied reflexively.** It has no more standing than its argument
earns. Where this document and SPEC.md disagree, **SPEC.md governs and this
document is wrong** (it is the advisory layer, never the source of truth).

**The crux, stated once.** EMET is a membrane in the literal, engineering sense
- a one-bit decision surface - but only at the **authentication** seam:
*do these bytes re-derive to the same hash, MATCH or DRIFT?* It deliberately
**refuses to become the authorization membrane** - the separate, normative
question of whether an authentic artifact *ought* to be allowed to cross. That
second question is a fact about a will and an authored policy, never a property
readable off the bytes. EMET locates that seam, decides the byte question, and
will not launder a byte-level `MATCH` into a permission. Everything below is, in
one way or another, a consequence of holding that line. (This crux recurs in
essays 01, 05, 06, and 08; it is stated in full only here.)

A SPEC-only reader can follow every essay: the [Orientation
primer](docs/rationale/00-orientation.md) and the
[Glossary](docs/rationale/GLOSSARY.md) define each term used, so you never need
to open `research/` to follow an argument.

---

## The one-page Rationale Map

Each EMET design element below is forced by a specific law. The **Status**
column marks whether the mapping is **load-bearing** (the law genuinely
constrains the design - remove it and EMET changes what it *is*) or
**illumination / lineage** (a figure that brands the intuition or names an
intellectual ancestor, but tests nothing on its own). The eight rows cover six
distinct essays; essays 01 and 03 each carry two rows.

| EMET element | Law | Essay | Status |
|---|---|---|---|
| Closed lattice; no `TRUSTED` (§2) | L1 No-Aseity | [02](docs/rationale/02-no-aseity.md) | load-bearing |
| `verify` MATCH/DRIFT; `refuse` strips in-band (§6.1) | L8 + membrane-errata | [01](docs/rationale/01-is-ought-seam.md) | load-bearing |
| Re-derivability; recomputed each `verify` (§8) | L11 Process>Property | [03](docs/rationale/03-occasionalism.md) | load-bearing |
| SHA-256 over exact raw bytes (§3) | L6 Intrinsic Substitution | [03](docs/rationale/03-occasionalism.md) | load-bearing |
| Zero actuation; undecided "for" (§6.6) | L2 + L3 | [04](docs/rationale/04-spoken-for.md) | load-bearing |
| Not its own root of trust (§11) | L1 reflexive | [05](docs/rationale/05-authored-root.md) | load-bearing |
| Advisory; attests, never adjudicates (§6.2,§6.4) | L8 + autonomy of the deontic | [01](docs/rationale/01-is-ought-seam.md) | load-bearing |
| The six boundaries as a set | emet/met/aleph | [06](docs/rationale/06-aleph.md) | literal (byte seam) / illumination (figure) |

**How to read a row.** "EMET element" is something you can point to in SPEC.md
or in the running code (the section reference is given). "Law" is the principle
that forces it, stated in the operator's vocabulary and unpacked in the linked
essay; the named thinkers behind each law appear there as further reading, never
as the reason to accept the row. "Essay" is the derivation. "Status" tells you
how much weight the mapping bears - and on the one row where a figure (the
*emet*/*met*/aleph image) does *no* logical work, that is marked explicitly, so
the metaphor never quietly absorbs a claim it hasn't earned.

---

## Reading order

The essays are written to be read in sequence, 00 → 08, but each also stands and
is refutable alone. Start at the primer; the headline (01) is the load-bearing
center; the walkthrough (07) is where the philosophy is shown actually running.

- **[00 - Orientation](docs/rationale/00-orientation.md)** - the five frames
  (no-aseity, the is/ought seam, teleosemantic deflationism, occasionalism, the
  spoken-*for*), plainly, for a reader who has only read SPEC.md.
- **[01 - The is/ought seam](docs/rationale/01-is-ought-seam.md)** *(headline)* -
  why `verify` decides the authentication bit and `refuse` won't let it launder
  into a permission: facts, not authority.
- **[02 - No-aseity → no `TRUSTED`](docs/rationale/02-no-aseity.md)** - why the
  verdict lattice is closed and can never emit `TRUSTED`: trust has no standing
  of its own.
- **[03 - Process over property → re-derivability](docs/rationale/03-occasionalism.md)** -
  why a verdict is recomputed per operation, nothing cached, no held key, and why
  the name is the hash.
- **[04 - The spoken-*for* → potential without intent](docs/rationale/04-spoken-for.md)** -
  why EMET stays a direction-neutral seed and authors no *for*; the operator is
  the only one who does.
- **[05 - The authored root → not its own root of trust](docs/rationale/05-authored-root.md)** -
  why EMET cannot certify itself and an external verifier must be the check of
  record.
- **[06 - *emet* / *met* / aleph → the smallest edge](docs/rationale/06-aleph.md)** -
  why the six boundaries, taken as a set, are what keep EMET from collapsing into
  the thing it exists to catch.
- **[07 - Walkthrough](docs/rationale/07-walkthrough.md)** - a runnable,
  re-derivable transcript of an authority-injection target passed through EMET,
  annotated step by step: the philosophy, operative.
- **[08 - Taxonomy](docs/rationale/08-taxonomy.md)** - where EMET sits among
  literal, isomorphic, and lineage "membranes," and exactly how much is claimed
  versus illustrated.

Top map: [docs/CURATION-INDEX.md](docs/CURATION-INDEX.md) - the top map tying this
philosophy layer to the scope-discipline engineering layer (and the new essays
09–14).

Supporting documents: the [Index](docs/rationale/INDEX.md) (this reading order
plus the map-row → essay table) and the [Glossary](docs/rationale/GLOSSARY.md)
(every corpus term defined, each with a provenance pointer).

---

## The close, applied to this document

By its own first principle, this rationale has no aseity. Its standing is
**conferred** - earned per argument, re-derived by the reader, and revocable the
moment a refuter lands - not self-grounded and not borrowed from the authority of
its sources. A documentary layer that asked to be believed on its own say-so
would be exactly the in-band authority claim EMET strips. So this document asks
for nothing of the kind. Re-derive it, or refute it.

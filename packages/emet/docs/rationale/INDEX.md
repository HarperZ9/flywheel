# Rationale -- Index

This is the reading-order index for the EMET rationale curation: a set of
derivation essays that show the existing EMET design as the worked
proof-of-concept of the corpus thesis. Each essay is a *derivation* you can
re-derive, not a warrant you must accept; `research/` is further reading only,
never authority-of-record. If an essay and [SPEC.md](../../SPEC.md) disagree,
SPEC governs and the essay is wrong.

Entry point: [RATIONALE.md](../../RATIONALE.md) (the spine -- framing note, the
one-page map, and reading order). This file expands the spine's map into a
row→essay table and lists every essay in order.

## Reading order (00 → 08)

- [00 -- Orientation](./00-orientation.md): the five frames (no-aseity, the is/ought seam, teleosemantic deflationism, occasionalism, the spoken-*for*) for a reader who never opens `research/`.
- [01 -- The Is/Ought Seam: Facts, Not Authority](./01-is-ought-seam.md): EMET does the authentication-grade byte decision and refuses the authorization crossing -- it *locates* the seam and won't launder across it.
- [02 -- No-Aseity: Why the Lattice Cannot Emit `TRUSTED`](./02-no-aseity.md): trust has no *svabhāva*; the verdict lattice is closed and conferral-dependent, never a `TRUSTED` value.
- [03 -- Process over Property: Re-derivability, and the Name that Is the Hash](./03-occasionalism.md): a verdict persists by no construction -- re-derived per operation, nothing cached, no held key -- and identity is intrinsic (the name is the hash).
- [04 -- The Spoken-*For*: Potential Without Intent](./04-spoken-for.md): EMET is the direction-neutral seed; the *for* is authored downstream by the operator, never by EMET.
- [05 -- The Authored Root: EMET Is Not Its Own Root of Trust](./05-authored-root.md): EMET cannot ground itself; an external verifier is the check of record -- integrity is *esse ab alio*.
- [06 -- The Aleph: The Boundaries as the Smallest Edge](./06-aleph.md): the six boundaries *are* the aleph -- the smallest edge that keeps *emet* (truth) from collapsing to *met* (death).
- [07 -- Worked Example: Authority Injection Through EMET](./07-walkthrough.md): the runnable transcript essay, annotating each command as the philosophy made operative -- EMET as the antidote to its own operating context.
- [08 -- Membrane Taxonomy: Where EMET Sits](./08-taxonomy.md): EMET placed as a *literal* engineered membrane in the authentication register, among literal / isomorphic / lineage membranes.

## New development (09 → 14)

The witness thesis made explicit. These essays do not restate 00–08; they develop
the material the [top index](../CURATION-INDEX.md) states in its §1 and §3 -- the
witness, the coordinate singularity, the atlas, spiral time, and the two truths.

- [09 -- Witnesses: Independence, One Witness Thrice](./09-witnesses.md): nothing is its own independent witness -- the compromised-substrate and same-author cases generalized; integrity is *witnessed*, not self-attested.
- [10 -- The Seam as a Coordinate Singularity](./10-coordinate-singularity.md): every single chart leaves a singularity it cannot see from inside itself; the self-audit's blind spot is structural, not a bug to patch.
- [11 -- The Atlas: No Single Chart Covers the Manifold](./11-the-atlas.md): truth is two-or-three *independent* charts whose overlap is the only place a fact is witnessed.
- [12 -- Spiral Time: Circular, Linear, the Spiral](./12-spiral-time.md): re-derivation is not a line but a return -- the verdict is re-conferred per operation, never held.
- [13 -- Two Truths: the Absolute and the Relative](./13-two-truths.md): the conventional register (the `MATCH` that is real and usable) and the ultimate register (no `MATCH` is self-standing); both true, at their own levels, without collapse.
- [14 -- Witness Walkthrough: The Witness Arc Made Runnable](./14-witness-walkthrough.md): the witness arc made runnable end to end -- the structural gate, the run as the independent witness, the located seam; the runnable companion to [07](./07-walkthrough.md).

## Lineage (where the membrane came from)

- [GENESIS.md](./GENESIS.md): EMET distilled from RAW's **coherence-membrane** oracle (a D3D11 ground-truth layer for an LLM's state-blindness) and the wider QUANTA-UNIVERSE ecosystem. The genesis doctrine -- *"observe inputs, reason locally, measure outputs; never assert runtime state, instrument it"* -- is mapped concept-by-concept onto EMET's six boundaries, and the origin documents are **anchored and re-derived (`MATCH`)** as a provenance pin. Clean-room: an idea re-stated in EMET's own words, no proprietary or reverse-engineered material incorporated.

## Map: EMET element → law → essay

The same eight rows as the [spine](../../RATIONALE.md), each linking the essay
that derives it. Status marks each mapping **load-bearing** vs
**illumination/lineage**, so "membrane" never becomes a universal solvent.

| EMET element | Law | Essay | Status |
|---|---|---|---|
| Closed lattice; no `TRUSTED` (§2) | L1 No-Aseity | [02](./02-no-aseity.md) | load-bearing |
| `verify` MATCH/DRIFT; `refuse` strips in-band (§6.1) | L8 + membrane-errata | [01](./01-is-ought-seam.md) | load-bearing |
| Re-derivability; recomputed each `verify` (§8) | L11 Process>Property | [03](./03-occasionalism.md) | load-bearing |
| SHA-256 over exact raw bytes (§3) | L6 Intrinsic Substitution | [03](./03-occasionalism.md) | load-bearing |
| Zero actuation; undecided "for" (§6.6) | L2 + L3 | [04](./04-spoken-for.md) | load-bearing |
| Not its own root of trust (§11) | L1 reflexive | [05](./05-authored-root.md) | load-bearing |
| Advisory; attests, never adjudicates (§6.2, §6.4) | L8 + autonomy of the deontic | [01](./01-is-ought-seam.md) | load-bearing |
| The six boundaries as a set | emet/met/aleph | [06](./06-aleph.md) | literal (byte seam) / illumination (figure) |

## Reference and apparatus

- [GLOSSARY.md](./GLOSSARY.md): every corpus term the essays use, each with one
  definition and a provenance pointer (provenance = further reading, never
  warrant). Read it alongside the Orientation primer to keep each essay
  self-contained.
- [walkthrough/](./walkthrough/): the regeneratable worked example. The
  stdlib-only harness [`render.py`](./walkthrough/render.py) runs the real EMET
  commands against the crafted fixture [`input.txt`](./walkthrough/input.txt) in
  an isolated sandbox and emits the committed
  [`transcript.txt`](./walkthrough/transcript.txt) byte-for-byte; essay
  [07](./07-walkthrough.md) embeds and annotates it.

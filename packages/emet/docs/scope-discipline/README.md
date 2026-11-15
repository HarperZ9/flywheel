# Scope Discipline - The Spine

> **What this curation is.** This is the engineering register of EMET's scope
> discipline: a six-gate litmus a maintainer runs on every pull request to answer
> one question - *will this change keep EMET an EMET, or quietly turn it into a
> different artifact wearing EMET's name?* The one-page operational rubric lives at
> [`../scope-discipline.md`](../scope-discipline.md); this directory expands it gate
> by gate. The philosophy that explains *why* the gates fall where they do - the
> witnesses, the coordinate-chart singularity, the is/ought seam - is a **sibling
> layer**, not a dependency, in [`../rationale/`](../rationale/INDEX.md). A
> maintainer who reads only this spine and [`../../SPEC.md`](../../SPEC.md) §6 can
> apply the whole rubric. The rationale is lineage; it is never the warrant.
>
> **Top map.** [`../CURATION-INDEX.md`](../CURATION-INDEX.md) - the top map tying
> this engineering layer to the rationale philosophy layer.
>
> **Status.** Operational, not normative. If this spine and `SPEC.md` ever
> disagree, **`SPEC.md` governs and this document is wrong.** Each gate stands or
> falls on whether it is grounded in a SPEC §6 boundary - not because this document,
> a thesis, or a maintainer asserts it. A rubric that justified EMET's no-authority
> shape *by appeal to its own authority* would be doing in-band exactly what EMET's
> `refuse` exists to strip.

---

## The thesis: integrity is witnessed, not self-attested

EMET's entire shape encodes one fact: **nothing can be its own independent
witness.** A compromised substrate re-derives a compromised self-hash and reports
itself clean. A same-author port agrees with its own authors' misreading, because
it inherited the misreading. One coordinate chart always leaves a singularity it
cannot see from inside itself. Integrity is therefore not a property a thing
*attests about itself* - it is a property *witnessed from outside*, by a position
the audited system does not host, control, or mediate. Every boundary below is one
face of that single fact.

From that fact follows the seam this whole curation governs: EMET grows in two
directions, and only one is safe.

- **The IS-AXIS is DEPTH, and it is the project's entire upside.** Depth is
  everything that makes a verdict *more re-derivable, more covered, better
  evidenced, more rigorously specified* - a tighter byte-hash core, more artifact
  and provenance facts under judgement, more conformance vectors, a second
  independent implementation, a sharpened MUST. Depth makes EMET *more of what it
  already is*: a verifier whose verdicts are facts. **EMET may grow without bound
  along this axis.**

- **The OUGHT-AXIS is WIDTH, and growth along it is DISQUALIFYING.** Width is the
  set of capabilities that would let EMET answer the question it exists to *refuse*
  - *ought this authentic signal cross?* Each is a way of acquiring standing EMET
  must never hold: **authority** (emitting a value that asserts permission),
  **adjudication** (taking or answering a model-safety or content decision),
  **inside position** (requiring to be hosted by the audited system),
  **enforcement** (allowing, denying, blocking of its own accord), **held key**
  (grounding a verdict in a secret rather than a re-derivation), and **actuation on
  the target** (editing, signing, reverting the artifact under judgement).

The asymmetry is structural, not stylistic. A width capability does not make EMET a
*worse* EMET along some dial of goodness; it moves EMET **across the seam** - from a
verifier that *locates* the is/ought boundary to a thing that *launders across* it.
That is why a feature can be genuinely useful and still be disqualifying: usefulness
is measured on the is-axis, but the cost is paid on the ought-axis, and the two do
not net. The six gates are the test that tells the two axes apart on a concrete diff.

---

## The six-gate map

Run every proposed change through all six gates. **Any NO is scope creep - no
matter how useful - and the change is out of scope until it is reshaped to a YES or
moved to a separate package.** The gates are not weighted and do not trade off:
they are six segments of one perimeter, and a perimeter with one segment open is
open.

| Gate | SPEC §6 boundary | Pass condition (one line) | Essay |
|---|---|---|---|
| **G1 - Re-derivable** | §6.5 (re-derivable) + §8 | Every verdict is reproducible from the same bytes, `spec_version`, and (marker-dependent only) `corpus_version` - no secret, no held key, no clock. | [G1-re-derivable.md](./G1-re-derivable.md) |
| **G2 - Closed lattice** | §6.1 (facts, not authority) + §2 | Every judgement is exactly one governed token (see below); nothing asserts authority, grants permission, or expresses a score. | [G2-closed-lattice.md](./G2-closed-lattice.md) |
| **G3 - Outside** | §6.3 (outside, never inside) | EMET runs from outside its target, reading it only by raw bytes; it requires no inside position in the system it audits. | [G3-outside.md](./G3-outside.md) |
| **G4 - Advisory** | §6.4 (advisory) + §6.6 (zero actuation) | Output stays data plus an exit code; EMET takes no action on the **audited target** of its own accord. The single actuator over the world is the operator. | [G4-advisory.md](./G4-advisory.md) |
| **G5 - Minimal TCB** | §10 (Trusted Computing Base) | The named core adds no third-party runtime dependency; integrations needing one live in a **separate package**. | [G5-minimal-core.md](./G5-minimal-core.md) |
| **G6 - No adjudication** | §6.2 (attests, never adjudicates) | No command takes or answers a model-safety or content decision; EMET operates only on artifact, byte, and provenance facts. | [G6-no-adjudication.md](./G6-no-adjudication.md) |

Each gate maps to one face of the witness thesis: G1 keeps the verdict
re-derivable by a *second* witness rather than re-confirmed by the *same* one; G3
keeps the witness *outside* the mediated view a compromised host would shape; G4
keeps EMET a witness rather than an *actor* on what it witnesses; and G2, G5, G6
keep the witness reporting *is*-facts only, never an authored *ought*.

---

## The governed verdict set

G2 is operable only against a *named* set. This is the closed universe of tokens
EMET may emit. **None of these is, or maps to, `TRUSTED`.** Each is a re-derivable
fact, never a grant of permission or a graded score. A change that emits a token
not on this list fails G2 until the token is removed or the set is amended **in
`SPEC.md` first** - never slipped into a frozenset to dodge the check.

| Surface | Governed tokens |
|---|---|
| Primary integrity lattice (`verify`, `anchor`) | `MATCH`, `DRIFT`, `UNVERIFIABLE` |
| `coherence` | `COHERENT`, `VIEW_DIFFERS_FROM_SOURCE` (`UNVERIFIABLE`) |
| `corroborate` | `CORROBORATED`, `QUARANTINE_READ_PATH_DIVERGENCE` (`UNVERIFIABLE` + reason) |
| `audit` (chain) | `INTACT`, `BROKEN` |
| monitor - per baseline / per file | `INTACT`, `CHANGED` / `MATCH`, `DRIFT`, `MISSING` |
| organs - perception / impedance | `UNCHANGED`, `DRIFTED`, `NEW`, `GONE` / `REVERTIBLE`, `NOT_REVERTIBLE` |

**This closure is now enforced STRUCTURALLY, not only by review.** Every governed
token is emitted through [`../../verdict.py`](../../verdict.py)'s
`governed(channel, token)`, which raises `VerdictError` if the token is not in that
channel's closed `frozenset` - and denies `TRUSTED` / `APPROVED` / `SAFE` (and
`ALLOWED` / `PERMITTED` / `AUTHORIZED` / `BLESSED` / `VERIFIED_AUTHORITY`) outright
via a belt-and-suspenders `FORBIDDEN` set. A codepath that tried to print a fourth
verdict fails at construction time inside the TCB, *before a byte reaches stdout*.
`governed()` returns the token **verbatim**, so it guards *what* may be emitted
without altering a single emitted byte. The monitor and organs auxiliary tokens -
ungoverned in earlier drafts, an oversight an adversarial scope review flagged - are
now **enumerated, not renamed**: the exact shipped tokens, placed explicitly inside
the governed universe so G2 has authority over the monitor and organs too. G2 is
therefore largely mechanical now; the one thing the type cannot catch is a
*genuinely needed* new verdict, which must be added to `SPEC.md` first - the
frozensets in `verdict.py` follow the spec, never the reverse.

---

## Reading order

1. **[depth-vs-width.md](./depth-vs-width.md)** - the is-axis / ought-axis seam in
   full: why depth is unbounded upside and width is disqualifying, and why the two
   do not net. Start here; it is the frame every gate inherits.
2. **The six gate essays, in order** - each re-derives one gate from its SPEC §6
   boundary, states why it is load-bearing, and gives its failure modes:
   [G1](./G1-re-derivable.md) · [G2](./G2-closed-lattice.md) ·
   [G3](./G3-outside.md) · [G4](./G4-advisory.md) · [G5](./G5-minimal-core.md) ·
   [G6](./G6-no-adjudication.md).
3. **[over-minimalism.md](./over-minimalism.md)** - the *symmetric* risk. Scope
   discipline fails in both directions: purity-as-uselessness (a verifier so
   guarded it verifies nothing anyone runs in anger) is as real as creep. The
   rubric governs the **seam, not a freeze**.
4. **[fix-the-spec.md](./fix-the-spec.md)** - when a gate blocks a genuinely needed
   capability, that is evidence about the **spec**, not a verdict against the
   capability. Inherited straight from `CONTRIBUTING.md`: *fix the spec, not the
   code* - amend `SPEC.md` and `conformance/vectors.json` together, openly, with
   vectors. Distinguishes legitimate repair of an *overstated* boundary from
   *relaxing a boundary's real content* to admit a convenient feature.
5. **[INDEX.md](./INDEX.md)** - the curation map: every file in this directory and
   how it relates to the others.

**One-page rubric:** [`../scope-discipline.md`](../scope-discipline.md) - the full
operational litmus (six gates, governed set, worked edge cases, the over-minimalism
section, and the refuter) on a single page. This spine is its table of contents and
unifying frame; the rubric is the page you run against a diff.

**Rationale (sibling layer, lineage only):**
[`../rationale/`](../rationale/INDEX.md) - the philosophy of the witness and the
coordinate-singularity seam:
[01-is-ought-seam](../rationale/01-is-ought-seam.md),
[02-no-aseity](../rationale/02-no-aseity.md),
[04-spoken-for](../rationale/04-spoken-for.md),
[06-aleph](../rationale/06-aleph.md). Read for *why* the seam falls where it does;
never cited as the *reason* to accept a gate.

---

*Further reading (lineage and grounding, never warrant):
[SPEC.md](../../SPEC.md) §§2, 5, 6, 8, 10, 11, 13, 14, 16;
[CONTRIBUTING.md](../../CONTRIBUTING.md) (the non-negotiable boundaries; "fix the
spec"); [THREAT-MODEL.md](../../THREAT-MODEL.md); the structural enforcement in
[verdict.py](../../verdict.py).*

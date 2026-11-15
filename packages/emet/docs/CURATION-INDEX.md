# The EMET Curation -- Top Index: Integrity Is Witnessed, Not Self-Attested

> **What this document is.** This is the single top index of the whole EMET
> documentary curation -- both layers, mapped once, with the through-line that
> joins them stated in full. It is a *derivation you can re-walk*, not a warrant
> you must accept. Nothing below is true because a corpus, a thesis, or a
> maintainer asserts it; each claim stands or falls on the argument given. Where
> it names `research/`, the code, or a thinker, that is *further reading and
> lineage* -- provenance for an intuition -- never the ground of a claim. A reader
> who knows only [`../SPEC.md`](../SPEC.md) can follow the whole of it. If this
> document and `SPEC.md` ever disagree, **`SPEC.md` governs and this document is
> wrong.**
>
> **Where it sits.** Below this index are two layers: the **PRACTICE** layer
> ([`./scope-discipline/`](./scope-discipline/README.md) -- the six gates a
> maintainer runs on a diff) and the **PHILOSOPHY** layer
> ([`./rationale/`](./rationale/INDEX.md) -- the derivation of *why* the design is
> shaped this way). This index is the philosophy of *both* read together; the
> material in §3 (the witness, the coordinate singularity, the atlas) is genuinely
> new -- it is not in essays 00–08 -- and is developed here, not restated.

---

## 1. The unifying thesis, stated once, in full

**Integrity is witnessed, not self-attested. Nothing can be its own independent
witness.**

Unfold it, because every line of both layers is a consequence of it.

To *attest* integrity is to claim "I am intact, I am what I was, I have not been
tampered with." The claim is cheap, and it is cheap for a precise reason: the
thing best positioned to make it is the thing least able to be believed when it
does. A compromised substrate re-derives a *compromised* self-hash with perfect
internal consistency and reports itself clean -- the math succeeds against the
tampered values, the audit chain reads INTACT, the self-test passes. A
same-author second implementation inherits its author's misreading and *agrees*,
confidently, in CI, on the wrong answer -- its agreement confirms self-consistency,
not correctness, because there was no independent model for the first to be
checked against. In both cases the failure mode is invisible to any check
conducted *from inside the thing that failed*, because self-agreement is exactly
what a competent compromise -- or a competent error -- produces for free. (This is
the load-bearing core of [`./rationale/05-authored-root.md`](./rationale/05-authored-root.md):
a thing checking itself on the substrate it would have to be independent of cannot
detect that substrate's compromise. **Confidence: high** -- it follows directly
from the absence of an independent model.)

So integrity is not a property a thing can *vouch for about itself*. It is a
property **witnessed from outside** -- established by a position the audited system
does not host, does not control, and does not mediate. The witness re-derives the
same fact from a vantage the failure could not have already corrupted: a second
machine the compromise did not touch, a second author the misreading did not
reach, a second chart whose coordinates make visible exactly what the first chart
could not see from inside itself. A `MATCH` is *real* -- true, checkable,
reproducible -- precisely *because* it is conferred by a relation a second party
can re-walk, and not asserted as an interior quality only the artifact's possessor
can confirm. Conferral-dependence is not weakness; it is the entire source of the
verdict's strength
([`./rationale/02-no-aseity.md`](./rationale/02-no-aseity.md): a conferred
`MATCH` is one you can *re-derive for yourself*, where a self-standing
trustworthiness would be one you'd have to *take on the artifact's word*).

This is why EMET refuses, at the type level, to emit `TRUSTED`. Trust would be a
self-standing fact a signal carries in itself -- an *aseity* -- and there is no such
fact for a byte comparison to read off. The lattice has three inhabitants --
`MATCH`, `DRIFT`, `UNVERIFIABLE` -- and no fourth that means "trust this," because
trust is not the kind of thing a witness *finds*; it is the kind of thing a will
*confers*, downstream, by an authored act EMET declines to perform. And it is why
EMET cannot be its own root of trust: `selftest` publishes a hash and *explicitly
asserts no authority over whether that hash should be believed* -- "re-derive it
from source to verify me" -- relocating the root of trust **outward**, to the
operator, the external verifier, and above all the independent re-derivation that
has not yet happened.

The shape that follows is the whole curation in one figure. A verifier of
integrity has a job that splits at a seam. On the near side is an **is-question**:
*do these bytes re-derive the anchored hash?* -- a fact about data, settled by
SHA-256, witnessable by anyone with the same bytes and no secret. On the far side
is an **ought-question**: *given that these bytes are authentic, should they be
admitted -- should the operator act?* -- which is not a fact about the data at all
but a fact about a will and a policy on the operator's side of the boundary. The
witness thesis is the discipline of staying on the is-side: EMET **witnesses the
is** and **refuses to author the ought**. Every gate in the practice layer and
every essay in the philosophy layer is one face of that single refusal.

(This thesis is stated in seed form in the practice layer's spine --
[`./scope-discipline/README.md`](./scope-discipline/README.md): "nothing can be
its own independent witness" -- and it is the figure the new philosophy essays
09–13 develop. The crux it inherits -- *EMET makes the authentication-grade byte
decision and refuses the authorization crossing* -- is the load-bearing claim of
[`./rationale/01-is-ought-seam.md`](./rationale/01-is-ought-seam.md) and is stated
in full once, in [`../RATIONALE.md`](../RATIONALE.md). **Status of this section:
load-bearing.**)

---

## 2. The two-layer map

The curation has two layers under this index. They are **siblings, not a
dependency**: the practice layer is complete on its own, and a maintainer who
reads only it plus `SPEC.md` §6 can apply the whole rubric. The philosophy layer
explains *why the gates fall where they do* -- it is lineage, never the warrant for
a gate. Read top-down for the why; read the practice layer alone to ship.

### 2.1 The PRACTICE layer -- the engineering (the WHAT-may-EMET-become)

[`./scope-discipline/`](./scope-discipline/README.md) -- the operable rubric a
maintainer runs on every pull request to answer one question: *will this change
keep EMET an EMET, or quietly turn it into a different artifact wearing EMET's
name?* The one-page litmus is [`./scope-discipline.md`](./scope-discipline.md);
the directory expands it gate by gate.

The frame is the **is-axis versus the ought-axis**
([`./scope-discipline/depth-vs-width.md`](./scope-discipline/depth-vs-width.md)).
Growth along the **is-axis is DEPTH** -- more re-derivability, more coverage,
better evidence, sharper spec -- and it is the project's whole upside; EMET may
grow without bound along it. Growth along the **ought-axis is WIDTH**, and it is
disqualifying: it is the set of capabilities that would let EMET *answer the
ought-question* it exists to refuse. The asymmetry is structural -- a width
capability does not make EMET a worse EMET on a dial of goodness; it moves EMET
**across the seam**, from a verifier that *locates* the is/ought boundary to a
thing that *launders across* it -- which is why a feature can be genuinely useful
and still disqualifying.

The **six gates** are the test that tells the two axes apart on a concrete diff.
Any NO is scope creep, no matter how useful; the gates are six segments of one
perimeter, and a perimeter with one segment open is open.

| Gate | SPEC §6 boundary | Pass condition (one line) | Essay |
|---|---|---|---|
| **G1 -- Re-derivable** | §6.5 + §8 | Every verdict reproduces from the same bytes, `spec_version`, and (marker-dependent only) `corpus_version` -- no secret, no held key, no clock. | [G1](./scope-discipline/G1-re-derivable.md) |
| **G2 -- Closed lattice** | §6.1 + §2 | Every judgement is exactly one governed token; nothing asserts authority, grants permission, or expresses a score. | [G2](./scope-discipline/G2-closed-lattice.md) |
| **G3 -- Outside** | §6.3 | EMET runs from outside its target, reading it only by raw bytes; it requires no inside position. | [G3](./scope-discipline/G3-outside.md) |
| **G4 -- Advisory** | §6.4 + §6.6 | Output stays data plus an exit code; EMET takes no action on the audited **target** of its own accord. | [G4](./scope-discipline/G4-advisory.md) |
| **G5 -- Minimal TCB** | §10 | The named core adds no third-party runtime dependency; integrations needing one live in a separate package. | [G5](./scope-discipline/G5-minimal-core.md) |
| **G6 -- No adjudication** | §6.2 | No command takes or answers a model-safety or content decision; EMET operates only on artifact, byte, and provenance facts. | [G6](./scope-discipline/G6-no-adjudication.md) |

The rubric also names its **symmetric failure mode**: scope discipline fails in
*both* directions
([`./scope-discipline/over-minimalism.md`](./scope-discipline/over-minimalism.md)).
**Over-minimalism -- purity-as-uselessness** -- a verifier so guarded it verifies
nothing anyone runs in anger -- is as real as creep. The rubric governs the
**seam, not a freeze**; refusing the JSON envelope, coverage expansion, or a
second implementation "to stay minimal" disqualifies EMET along the is-axis the
way creep disqualifies it along the ought-axis. And when a gate genuinely blocks a
needed capability, that is **evidence about the spec, not a verdict against the
capability**
([`./scope-discipline/fix-the-spec.md`](./scope-discipline/fix-the-spec.md)):
amend `SPEC.md` and `conformance/vectors.json` together, openly, with vectors --
never route around a gate by slipping in an unsanctioned token, write, or
dependency.

### 2.2 The PHILOSOPHY layer -- the derivation (the WHY)

[`./rationale/`](./rationale/INDEX.md) -- derivation essays that show the existing
EMET design as the worked proof of the witness thesis. The spine is
[`../RATIONALE.md`](../RATIONALE.md) (framing note, the one-page map, reading
order); the reading-order index is
[`./rationale/INDEX.md`](./rationale/INDEX.md).

**The original derivation (00–08)** -- the why of the design as it stands. Read in
sequence, but each stands and is refutable alone.

| # | Essay | What it derives |
|---|---|---|
| 00 | [Orientation](./rationale/00-orientation.md) | The five frames, for a SPEC-only reader. |
| 01 | [The is/ought seam](./rationale/01-is-ought-seam.md) *(headline)* | EMET makes the authentication byte decision and refuses the authorization crossing -- facts, not authority. |
| 02 | [No-aseity → no `TRUSTED`](./rationale/02-no-aseity.md) | Trust has no own-being; the lattice is closed and conferral-dependent. |
| 03 | [Process over property](./rationale/03-occasionalism.md) | A verdict is re-derived per operation -- nothing cached, no held key -- and the name is the hash. |
| 04 | [The spoken-*for*](./rationale/04-spoken-for.md) | EMET is the direction-neutral seed; the *for* is authored downstream by the operator. |
| 05 | [The authored root](./rationale/05-authored-root.md) | EMET cannot be its own root of trust; an external verifier is the check of record. |
| 06 | [The aleph](./rationale/06-aleph.md) | The six boundaries *are* one edge -- the smallest one whose removal kills, not weakens. |
| 07 | [Walkthrough](./rationale/07-walkthrough.md) | The philosophy made operative -- a runnable, re-derivable transcript. |
| 08 | [Taxonomy](./rationale/08-taxonomy.md) | EMET placed as a *literal* engineered membrane in the authentication register. |

**The new development (09–14)** -- the witness thesis made explicit. These essays
are *not* a restatement of 00–08; they develop the material this index states in
§1 and §3 -- the witness, the coordinate singularity, the atlas, and the two
registers of truth a verdict travels in. They are the philosophy layer's account
of *why the seam falls where it does* in the practice layer's gates.

| # | Essay | What it develops |
|---|---|---|
| 09 | [Witnesses](./rationale/09-witnesses.md) | Nothing is its own independent witness -- the compromised-substrate and same-author cases generalized; integrity is *witnessed*, the conferred-not-attested core of §1. |
| 10 | [Coordinate singularity](./rationale/10-coordinate-singularity.md) | Every single chart leaves a singularity it cannot see from inside itself; the self-audit's blind spot is structural, not a bug to patch. |
| 11 | [The atlas](./rationale/11-the-atlas.md) | Truth is two-or-three *independent* charts whose overlap is the only place a fact is witnessed; corroboration and the independent re-implementation are the atlas made operational. |
| 12 | [Spiral time](./rationale/12-spiral-time.md) | Re-derivation is not a line but a return -- the verdict is re-conferred per operation, never held; identity recurs without being stored. |
| 13 | [Two truths](./rationale/13-two-truths.md) | The conventional register (the `MATCH` that is real and usable) and the ultimate register (no `MATCH` is self-standing); both true, at their own levels, without collapse. |
| 14 | [Witness walkthrough](./rationale/14-witness-walkthrough.md) | the witness arc made runnable end to end (the structural gate, the run as the independent witness, the located seam); the runnable companion to essay 07. |

> **Status note on 09–14.** These essays are the named deliverables of the
> witness-thesis development, and all of them are now present in `./rationale/`.
> Each is held to the same fidelity as 00–08 (re-derivable argument,
> objection→answer, refuter, marked load-bearing vs illumination) and to
> `SPEC.md` as governing. **Confidence on the 09–14 scope as stated: this index
> defines it; the essays derive it.**

Reference apparatus, shared by both blocks:
[`./rationale/GLOSSARY.md`](./rationale/GLOSSARY.md) (every corpus term, each with
a provenance pointer) and the regeneratable
[walkthrough](./rationale/07-walkthrough.md) transcript.

---

## 3. The through-line: the seam, the witness, the atlas, and the gates

This is the load-bearing section -- the argument that the two layers are one
thing seen twice. It runs in four moves.

### 3.1 The seam -- where the third-person inventory hits its limit

Start where the is/ought seam already is
([`./rationale/01-is-ought-seam.md`](./rationale/01-is-ought-seam.md)). A signal
arriving at a boundary admits two questions in two non-interchangeable
vocabularies. **Authentication** speaks only of *is*: these bytes are, or are not,
those bytes -- answerable off the signal, a literal 1 or 0. **Authorization**
speaks of *may*, *ought*, *permitted* -- and no valid inference carries you from
the first vocabulary to the second, because a valid inference introduces no
non-logical vocabulary its premises did not already contain (the *autonomy of the
deontic*). The *ought* is not hiding in the bytes waiting to be found; it has to
be **authored**, by an operator subscribing to a policy, on the near side of the
boundary.

Now press the third-person inventory as far as it goes. List every is-fact about
the signal: its bytes, its hash, its provenance, every measurable property. The
inventory is complete, and it still does not contain a single *ought*. This is not
a gap that more inventory closes; it is the point at which the third-person
description *runs out of the vocabulary it would need* to answer the next
question. The seam is exactly that limit -- the place where "what is the case about
this signal" has said everything it can say and the question "what may be done"
has not yet been touched. EMET sits on the is-side of that limit by construction
and refuses to cross it. (**Load-bearing.** The capability objection -- "in an
object-capability system, holding the token *is* authorization" -- does not break
this: a capability is a *materialized grant*, an *ought* minted at an earlier act
of issuance and frozen into bytes; the seam **relocates to issuance**, it does not
vanish. The witness still witnesses an *is* -- the token's bit-integrity -- and
declines the *ought* of whether it was validly issued.)

### 3.2 The witness -- you cannot be your own

The seam tells you EMET must report an *is* and refuse an *ought*. The witness
thesis tells you *who may report the is* -- and the answer is never the thing
reporting on itself.

Run the limit reflexively. EMET checks artifacts by re-deriving a fact and
reporting it: a relay. When EMET checks *itself*, it is tempted to become the
root -- the seam that authorizes its own authority. But the root of a trust chain
is, by definition, the one element *not validatable from within the chain*, and a
thing validating itself is transparently validation from within the chain. The
self-test that "passes" on a compromised substrate is not evidence of integrity;
it is evidence that the compromise was competent enough to make the math succeed
against its own tampered values. **The witness has to be outside the failure mode
it would detect** -- a different machine for substrate compromise, a different
author for authorial misreading, because in each case the would-be witness is
otherwise *not independent of the very thing it is testing*
([`./rationale/05-authored-root.md`](./rationale/05-authored-root.md) §3, §5.2;
[`./rationale/09-witnesses.md`](./rationale/09-witnesses.md) generalizes it).

This is why EMET's most reflexive act, `selftest`, publishes a credential and
**declines to certify it** -- and why `SPEC.md` §11 names the external verifier as
the check of record and the independent re-implementation as the not-yet-satisfied
open deliverable. Self-agreement carries **zero independent confirmatory weight**;
the only agreement that counts is agreement across models that share nothing. (The
practice layer says the same thing structurally:
[`./scope-discipline/README.md`](./scope-discipline/README.md) -- "G1 keeps the
verdict re-derivable by a *second* witness rather than re-confirmed by the *same*
one; G3 keeps the witness *outside* the mediated view a compromised host would
shape." **Load-bearing.**)

### 3.3 The atlas -- truth is two-or-three independent charts

If no single witness suffices, what does? An **atlas** -- more than one chart, each
independent, with truth living in their overlap.

The figure is exact, not decorative
([`./rationale/10-coordinate-singularity.md`](./rationale/10-coordinate-singularity.md),
[`./rationale/11-the-atlas.md`](./rationale/11-the-atlas.md)). Any single
coordinate chart over a curved space carries a **singularity** -- a point its own
coordinates cannot represent, invisible from inside the chart, not because the
space is broken there but because *the chart is*. The fix is never a better single
chart; it is a *second* chart whose coordinates are well-behaved exactly where the
first's fail, and the two agree on their overlap. A self-audit is a single chart:
it has a blind spot at precisely the place it would need to stand outside itself to
see, and no amount of refining the one chart removes it. Two independent
charts -- two witnesses that share no model -- cover each other's singularities, and
a fact attested in their **overlap** is witnessed in a way neither alone could
provide.

EMET already runs this. `corroborate` reads the target along **disjoint read
paths** and reports `CORROBORATED` only when they agree, or
`QUARANTINE_READ_PATH_DIVERGENCE` when they do not -- an atlas of read paths, where
the divergence *is* the singularity made visible. The call for an **independent
second implementation** is the atlas at the level of authorship: the reference and
a from-the-spec-alone re-derivation are two charts; their agreement on every vector
converts re-derivability from *asserted* to *demonstrated*. (Two further charts
worth naming as the development matures:
[`./rationale/12-spiral-time.md`](./rationale/12-spiral-time.md) -- the verdict
re-conferred *per operation* rather than held is a chart in *time*, where each
return is an independent re-derivation rather than a cached trust read back; and
[`./rationale/13-two-truths.md`](./rationale/13-two-truths.md) -- the conventional
register in which a `MATCH` is real and usable and the ultimate register in which
no `MATCH` is self-standing are two charts on the *same* verdict, both true at
their own level, neither collapsing into the other. **Status: the atlas/coordinate-
singularity figure is load-bearing for the corroboration and independent-
implementation derivations; the curved-space imagery itself is illumination --
it brands the structural fact that one chart cannot witness its own singularity,
and tests nothing on its own.**)

### 3.4 The gates are the engineering of exactly this

Now the join. The six scope-discipline gates are not six tasteful constraints; they
are the witness thesis compiled into a litmus a maintainer can run on a diff. Each
gate keeps one face of "witnessed, not self-attested" from being quietly removed.

- **G1 (re-derivable)** keeps the verdict witnessable by a *second* party rather
  than confirmed by the *same* one. A held key or a cached "good last time" makes
  the verdict a property the tool *has* -- self-attested -- instead of a fact a
  second witness can *re-derive*. G1 is §3.2's "second machine," made mechanical.
- **G3 (outside)** keeps the witness *outside* the mediated view a compromised host
  would shape -- the §3.2 "different machine," and §3.3's refusal to let the chart
  being audited also *be* the coordinate system you read it in.
- **G4 (advisory) and G6 (no adjudication)** keep EMET a **witness rather than an
  actor**: the moment a `MATCH` opens a gate or a command answers "is this content
  safe," EMET has authored the *ought* the seam (§3.1) forbids it -- it has stopped
  witnessing the is and started conferring the for.
- **G2 (closed lattice)** keeps the witness reporting an *is*, never a self-standing
  *trust*: `TRUSTED` is the aseity §1 denies, welded out of the output type.
- **G5 (minimal TCB)** keeps the witness *re-implementable* -- keeps the second
  chart of §3.3 *cheap enough to actually draw*, because every third-party import is
  surface a second author must reproduce or trust, and trust is the thing EMET
  refuses.

And the **over-minimalism** caution is the witness thesis guarding its *other*
flank: a witness so guarded it witnesses nothing real has kept its independence by
having nothing to be independent *about*. Depth -- more, harder, real targets; the
machine-readable envelope; the second implementation -- is *required* growth,
because a witness that never witnesses anything anyone runs in anger is witnessing
a sandbox, not the world. The seam the rubric governs is the same seam this whole
index turns on; the gates are where it is held against a concrete change.
**Status of §3.4: load-bearing -- it is the claim that the two layers are one
discipline.**

---

## 4. Suggested reading paths

Pick the path that matches why you are here. Each is a route through the two
layers above; none requires opening `research/`.

- **The maintainer with a diff in hand (ship-it path).** Go straight to the
  practice layer:
  [`./scope-discipline.md`](./scope-discipline.md) (the one-page litmus) →
  run all six gates → if a gate blocks something you believe is needed, read
  [`./scope-discipline/fix-the-spec.md`](./scope-discipline/fix-the-spec.md). You
  never need the philosophy layer to apply the rubric; `SPEC.md` §6 and the
  governed set are enough.

- **The reader who wants the why before the what (derivation path).** Read this
  index §1 → §3 → then the philosophy layer in order:
  [`../RATIONALE.md`](../RATIONALE.md) (spine) →
  [00](./rationale/00-orientation.md) →
  [01](./rationale/01-is-ought-seam.md) (the headline) →
  02–08 → the new development
  [09](./rationale/09-witnesses.md)–[13](./rationale/13-two-truths.md). The
  [walkthrough](./rationale/07-walkthrough.md) is where the philosophy is shown
  running.

- **The skeptic (refuter-first path).** Each load-bearing claim names the
  observation that would break it. Read the refuters first:
  [02](./rationale/02-no-aseity.md) (a verdict outside the lattice),
  [05](./rationale/05-authored-root.md) (authentication all the way down -- relay
  with no authored root),
  [06](./rationale/06-aleph.md) (a boundary droppable with no change to what EMET
  *is*), and the rubric's own refuter in
  [`./scope-discipline.md`](./scope-discipline.md) (a change that passes all six
  gates yet crosses the seam, or fails a gate yet changes nothing). If none
  triggers, the curation earns its keep; if one does, it is actionable, not
  decorative.

- **The witness-thesis path (this index's own spine).** §1 (the thesis) →
  [09 Witnesses](./rationale/09-witnesses.md) →
  [10 Coordinate singularity](./rationale/10-coordinate-singularity.md) →
  [11 The atlas](./rationale/11-the-atlas.md) →
  [12 Spiral time](./rationale/12-spiral-time.md) →
  [13 Two truths](./rationale/13-two-truths.md) →
  [14 Witness walkthrough](./rationale/14-witness-walkthrough.md) → back to §3.4 to
  see the gates as its engineering. This is the new material; read it as
  development, not review.

---

## 5. The close, applied to this index

By its own thesis, this index has no aseity. It is not true because it sits in a
`docs/` folder, nor because a corpus lends it standing -- it has exactly the
authority its argument earns under your attempt to break it, and not one byte
more. A top index that asked to be believed on its own say-so would be doing,
in band, precisely the self-attestation the whole curation exists to refuse: a
document witnessing its own integrity. So it asks for nothing of the kind. The
witness it points to is **outside** it -- the SPEC it is governed by, the code it
cites, the second reader who re-derives the through-line and finds it holds or
finds the seam where it fails. Re-derive it, or refute it. That is the only
standing it ever had -- and, the thesis says, the only standing anything ever has.

---

*Further reading (lineage and grounding, never warrant):
[`../SPEC.md`](../SPEC.md) §§2, 6, 8, 11, 12, 13;
[`../RATIONALE.md`](../RATIONALE.md) (the spine);
[`../CONTRIBUTING.md`](../CONTRIBUTING.md) (the non-negotiable boundaries; "fix
the spec"); [`../THREAT-MODEL.md`](../THREAT-MODEL.md). Practice layer:
[`./scope-discipline/README.md`](./scope-discipline/README.md),
[`./scope-discipline/INDEX.md`](./scope-discipline/INDEX.md),
[`./scope-discipline.md`](./scope-discipline.md). Philosophy layer:
[`./rationale/INDEX.md`](./rationale/INDEX.md) and essays
[00](./rationale/00-orientation.md)–[13](./rationale/13-two-truths.md).*

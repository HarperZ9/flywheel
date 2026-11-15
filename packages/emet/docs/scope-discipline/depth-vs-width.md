# Depth vs Width: The Is-Axis and the Ought-Axis

> **Status of this document.** This is a derivation, not a warrant. Nothing below
> binds because a corpus, a thesis, or a maintainer asserts it; every claim is
> offered to be **re-derived** against [SPEC.md](../../SPEC.md) §6 and the
> boundaries [CONTRIBUTING.md](../../CONTRIBUTING.md) makes non-negotiable. Where
> it points elsewhere -- to the code, to the rationale curation in
> [../rationale/](../rationale/), to `research/` -- it points as *further reading*,
> lineage and provenance, **never** as the reason to accept a claim. If this
> document and `SPEC.md` ever disagree, **`SPEC.md` governs and this document is
> wrong.** A reader who knows only `SPEC.md` should be able to follow the whole of
> it; the one-page rubric is [../scope-discipline.md](../scope-discipline.md), the
> spine is [./README.md](./README.md), and the six gates that operationalize this
> frame are [./G1-re-derivable.md](./G1-re-derivable.md) through
> [./G6-no-adjudication.md](./G6-no-adjudication.md).

---

## Why this essay exists, and why it is not the rubric again

The one-page rubric ([../scope-discipline.md](../scope-discipline.md)) already
states the frame in its §1: there is an is-axis and an ought-axis, depth is safe,
width is disqualifying, and the asymmetry is structural. If this essay only
restated that, it would be **bloat** -- the over-minimalism-in-reverse failure the
rubric itself names in its §5, where doc-mass outweighs the thing it describes.
So this essay earns its place only by doing what a one-page litmus cannot afford
the room to do: ground the frame in EMET's *actual code* and in *this project's
real history* -- the named fixes, the corrected overstatements -- develop the
strongest objection and answer it, give a refuter, and **stop** when the
argument returns nothing new (this is the authored stop, L14: a section ends when
it has nothing left to add, and padding past that point is its own small breach
of fidelity).

The rubric is the *litmus*. This essay is the *frame the litmus runs on*. The six
gates ([./G1-re-derivable.md](./G1-re-derivable.md),
[./G2-closed-lattice.md](./G2-closed-lattice.md),
[./G3-outside.md](./G3-outside.md),
[./G4-advisory.md](./G4-advisory.md),
[./G5-minimal-core.md](./G5-minimal-core.md),
[./G6-no-adjudication.md](./G6-no-adjudication.md)) are six segments of the
ought-axis perimeter; this essay is the argument that the perimeter is the right
shape and that the asymmetry between the two axes is not a stylistic preference
but a structural fact about what EMET *is*.

---

## The unifying fact: integrity is witnessed, not self-attested

EMET's entire shape encodes one fact, and the depth/width frame is that fact read
as a roadmap rule. The fact is: **nothing can be its own independent witness.** A
compromised substrate re-derives a compromised self-hash and reports itself sound
(SPEC §11, trust-root regress); a same-author second port agrees with its own
author's misreading and so demonstrates internal consistency, not re-derivability
(SPEC §12); one coordinate chart always leaves a singularity it cannot see from
the inside. This is why `selftest` emits an identity and explicitly *not* a
verdict (SPEC §13, §14), why the highest-leverage contribution is a
*different-author* implementation ([CONTRIBUTING.md](../../CONTRIBUTING.md)), and
why EMET must read its target from *outside* by raw bytes (SPEC §6.3).

Now apply that fact to EMET's own growth. **Depth is the project becoming a better
witness; width is the project trying to become the thing it witnesses.** Every
is-axis move makes EMET more re-derivable, more covered, better evidenced, more
rigorously specified -- it sharpens the witness. Every ought-axis move gives EMET
standing *over* the thing it judges -- authority, adjudication, an inside position,
enforcement, a held key, actuation on the target -- which is precisely the standing
a witness must not hold, because a witness with standing over the witnessed has
become a second author rather than an independent check. The same fact that
forbids EMET from being its own root of trust forbids EMET from growing along the
ought-axis: in both cases the move collapses the gap between the checker and the
checked, and the gap is the whole instrument.

This is the engineering register. The philosophy that grounds it -- the witness,
the is/ought seam, the coordinate-singularity that no single chart escapes -- is a
sibling layer in [../rationale/](../rationale/), cited here as lineage and never
as warrant. A reader who rejects every philosophical figure loses vividness and a
second road to the same place, not one step of the argument below.

---

## The two axes, named precisely

EMET grows in two directions, and only one of them is safe. The discipline is the
refusal to confuse growth along the first with growth along the second.

**The is-axis is DEPTH, and it is the project's whole upside.** The is-axis is
everything that makes a *fact* more re-derivable, more covered, better evidenced,
more rigorously specified. It is the axis on which EMET becomes *more of what it
already is*:

- **re-derivability** -- tightening the byte-hash core; pinning a scan that was
  implicit (SPEC §16's non-overlapping-leftmost rule was exactly such a deepening,
  worked below); closing a gap a second implementation surfaced;
- **coverage** -- more artifact, byte, and provenance facts brought under
  judgement; more disjoint read paths for `corroborate`; more honest
  `UNVERIFIABLE` reason codes where inability was previously silent;
- **evidence** -- more conformance vectors; a machine-readable envelope so a
  consumer re-derives without reading reference code; a second *independent*
  implementation (the highest-leverage contribution there is);
- **spec rigor** -- sharper MUSTs; a corrected overclaim; a disclosed limit
  (SPEC §11) made more precise rather than quietly dropped.

Every one of these leaves the verdict lattice closed (SPEC §2), the actuator
single (SPEC §6.6), and the position outside (SPEC §6.3). **EMET can grow without
bound along this axis.** Depth is not merely permitted; some of it is *required*
growth -- refusing it is the over-minimalist failure, treated in its own section
below.

**The ought-axis is WIDTH, and growth along it is DISQUALIFYING, with no amount of
utility able to redeem it.** The ought-axis is the set of capabilities that would
let EMET answer the question it exists to *refuse* -- *ought this authentic signal
cross?* Each is a way of acquiring standing EMET must never hold, and each maps to
a gate:

- **authority** -- emitting a value that asserts permission (`TRUSTED`, `APPROVED`,
  `SAFE`, a trust score). → [G2](./G2-closed-lattice.md)
- **adjudication** -- taking a model-safety or content decision as input, or
  answering one. → [G6](./G6-no-adjudication.md)
- **inside position** -- requiring to be hosted by, or routed through, the audited
  system. → [G3](./G3-outside.md)
- **enforcement** -- allowing, denying, blocking, or gating of EMET's own accord.
  → [G4](./G4-advisory.md)
- **held key** -- grounding a verdict in a secret, a cached trust, a credential the
  tool *has* rather than re-derives. → [G1](./G1-re-derivable.md)
- **actuation on the target** -- editing, writing, signing, backing up, or
  reverting the artifact under judgement. → [G4](./G4-advisory.md)

(G5, the stdlib-only-core gate, is not itself an ought-axis capability; it is the
gate that keeps the *witness auditable* -- the minimal TCB a second author must
reproduce. It guards the is-axis precondition that makes all the others
checkable. See [./G5-minimal-core.md](./G5-minimal-core.md).)

---

## The asymmetry is structural, not a continuous dial

This is the heart of the frame, and it is the one thing the rubric's §1 states but
cannot, in one page, *prove*. The claim:

> A capability on the ought-axis does not make EMET a **worse** EMET along some
> continuous dial of goodness. It moves EMET **across the seam** -- from a verifier
> that locates the is/ought boundary to a thing that launders across it. That is
> why a feature can be genuinely **useful** and still be **disqualifying**:
> usefulness is measured on the is-axis, but the cost is paid on the ought-axis,
> and the two do not net. [Status: **load-bearing**.]

The phrase that does the work is *the two do not net*. A continuous-dial model
would say: this feature scores +7 in utility and −3 in purity, net +4, ship it.
That model is exactly the error. The two axes are not commensurable, because they
measure two different *categories* of thing.

Here is the structural reason, in three steps a SPEC-only reader can check.

**Step 1 -- the is-axis measures a property of the verdict; the ought-axis changes
the category of the artifact.** A deeper marker corpus, a JSON envelope, a tighter
hash core -- these change *how good a fact EMET reports*. They are quantitative:
the verdict is the same kind of thing, only more re-derivable or more consumable.
A `TRUSTED` token, an inside position, an auto-revert -- these change *what kind of
thing EMET is*. They are categorical: the output type now carries an
authorization, the read is now mediated, the verdict now acts. You cannot trade a
quantity of the first against a quantity of the second, because the second is not
a quantity. It is a phase change.

**Step 2 -- the closed perimeter has no interior.** The six boundaries are one edge
cut six ways ([../rationale/06-aleph.md](../rationale/06-aleph.md)): the perimeter
is closed *only* all-six-at-once, and a perimeter with one segment open is not a
smaller perimeter -- it is an opening. An opening confers nothing; it is just a
wire that data crosses. So there is no "slightly open" state to land in. A change
either keeps the perimeter closed (depth, or a neutral is-axis move) or it opens
the perimeter (width). There is no third region where a useful breach sits being
80%-fine. This is why the gates "are not weighted and do not trade off against
each other" (rubric §2): a weighting presupposes an interior to interpolate
across, and there is none.

**Step 3 -- the useful breach is the *most* dangerous one, not the most forgivable.**
The continuous-dial intuition says a useful violation is a closer call, more
deserving of an exception. The structural fact says the opposite. A *useless*
breach of the perimeter gets caught and reverted because nobody is arguing for it.
A *useful* breach is the one that recruits an advocate -- "but it would help so
much" -- and a useful breach, once admitted, sets the precedent that the *next*
useful breach can argue from. Review cannot distinguish a harmless unenumerated
token from a harmful one once the precedent "useful tokens may be slipped in" is
established (rubric §6, step 1). The utility is not a mitigating factor; it is the
attack surface. **This is the load-bearing inversion of the continuous-dial model,
and it is the reason the asymmetry must be stated as a category boundary rather
than a tradeoff.**

So when a contributor says "feature X passes every gate but G4, and it's so
useful," the disciplined response is not "let's weigh the utility against the G4
cost." It is: "the utility is real and is measured on the is-axis; the G4 cost is
categorical and is paid on the ought-axis; they do not net; reshape X to live on
the is-axis (or in a separate package) or it is out of scope, *however useful*."

---

## Grounding in L3 and the emet/met aleph

The asymmetry is not a security taste. It is forced by two laws the rationale
curation derives, and naming them is what keeps this essay from being an
engineer's aesthetic dressed as a principle.

**L3 -- direction-neutral generativity: the more a seed can do, the less it is
*for*.** ([../rationale/04-spoken-for.md](../rationale/04-spoken-for.md) derives
this from L2/L3.) There is an inverse relation between how generative an instrument
is and how much direction it carries intrinsically. A pile of sand can become
glass, a mold, a filter, an hourglass -- maximally generative, minimally *for*
anything; a finished hourglass is *for* timing and almost nothing else, having
spent its generativity buying direction. Maximal generativity *is* minimal
intrinsic purpose.

Map this onto the two axes and the asymmetry falls out. **Every ought-axis
capability is a purpose baked into the seed.** "Auto-revert on DRIFT," "emit
`TRUSTED`," "block on divergence," "host inside the target," "answer is-this-safe"
-- each is a standing answer to *what the verdict is for*, and each spends EMET's
generativity to buy a direction. An ought-axis move is L3 run in reverse: it
converts a direction-neutral seed into a directed primitive -- "a dead abstraction,
good for one purpose and adoptable by no one who wants a different purpose"
([../rationale/04-spoken-for.md](../rationale/04-spoken-for.md)). This is *why*
usefulness does not redeem it: the usefulness is precisely the direction, and the
direction is precisely what disqualifies a tool meant to stay a seed. The market
corollary the rationale notes -- minimal *for* **is** maximal adoptability, so a
regulator and a frontier lab and that lab's competitor can all point the same seed
at their own artifacts -- is the same law read economically. (That corollary is
illumination, not warrant: it shows the law's reach, it does not justify the gate.)

The is-axis, by contrast, does *not* spend generativity. A deeper corpus, a JSON
envelope, more vectors -- none of these decides what a verdict is *for*. They make
the *for*-free seed a better *for*-free seed. So depth grows the witness without
authoring a purpose into it; width authors a purpose and thereby stops the witness
being a witness. That is the L3 statement of "the two do not net": depth and width
are not two amounts of one currency, they are presence-of-direction versus
absence-of-direction, and you cannot net a presence against an absence.

**The emet/met aleph -- remove an edge and it becomes the thing it exists to
catch.** ([../rationale/06-aleph.md](../rationale/06-aleph.md) develops the figure
and fences it as lineage.) The Hebrew *emet* (truth) is written aleph–mem–tav;
strike the leading *aleph* -- phonetically the lightest mark in the alphabet, a
near-soundless glottal stop -- and what remains is *met* (dead). The figure brands
an intuition the code already carries: an edge can be near-nothing in substance
and total in consequence.

The depth/width application is exact. **The ought-axis boundary is EMET's aleph: a
near-nothing edge whose removal does not weaken EMET but converts it into the
artifact it exists to catch.** EMET exists to catch the signal weaponized against
a layer that mistook authentication for authorization -- the in-band authority
claim, the laundered *ought*. Remove Boundary 1 and let the lattice emit `TRUSTED`,
and EMET is now *itself* a thing that asserts authority off a fact it
authenticated: it has become the exact failure mode it was built to detect. The
ought-axis move does not make EMET a flawed catcher of the weaponized signal; it
makes EMET *into* the weaponized signal -- an authentication fact wearing an
authorization it was never entitled to. That total-consequence-from-near-nothing
is why the asymmetry cannot be a dial. A dial has degrees; the aleph has two
states, *emet* and *met*, truth that witnesses and the edgeless thing that does
not. [Status of the figure: **illumination / lineage** -- it names the structural
fact memorably and tests nothing. The structural fact (Step 2 above; the closed
perimeter) is **load-bearing** and survives the figure's deletion intact.]

---

## Grounded in the code, and in this project's real history

The frame is not abstract. It is legible in EMET's source and in the named fixes
this project actually made. Each of the following is checkable against the files
cited.

### Depth, made structural: `governed()` (`verdict.py`)

Boundary 1 -- *facts, not authority* -- was, until recently, enforced by **review**:
the verdict tokens were bare string literals scattered through `membrane.py` and
`monitor.py`, so emitting an unsanctioned `TRUSTED` would have been a review miss,
not a construction error. The fix routed every governed emission through
`verdict.py`'s `governed(channel, token)` (`verdict.py:87`), which raises
`VerdictError` if the token is not in that channel's closed frozenset and denies
`TRUSTED`/`APPROVED`/`SAFE`/`ALLOWED`/`AUTHORIZED`/… outright (`verdict.py:75`,
the `FORBIDDEN` set; `:95`, the guard). A codepath that tried to print a fourth
verdict now fails at construction time, inside the named-core TCB, *before a byte
reaches stdout*.

This is the cleanest possible illustration of **pure depth**. `governed()` returns
the token *verbatim* (`verdict.py:104`): it changes *how* a token is emitted,
never *what* -- every stdout byte is unchanged. It added no third-party dependency
(the module has no imports at all), no new verdict, no authority, no actuation. It
moved the closed-lattice guarantee from a property a reviewer must *re-establish
each PR* to a fact the type *re-derives at construction*. That is the is-axis
exactly: the same verdict, more re-derivable, more covered by structure. It is the
DEPTH face of [G2](./G2-closed-lattice.md), and it is why G2 is "largely mechanical
now" -- though a reviewer still applies it by hand to the one thing the type cannot
catch: a genuinely needed new verdict must be added to the **governed set in
`SPEC.md` first**, never slipped into a frozenset to dodge the check.

### Depth, surfaced by a second author: the non-overlapping-leftmost scan (`corpus.py`)

The marker *count* was once unpinned. SPEC §16 records the history plainly: an
independent reimplementation surfaced that "count" was ambiguous -- what happens
when markers overlap, or repeat? The fix pinned a **non-overlapping leftmost scan
in corpus order** (`corpus.py:73`, `def scan`): scan the raw bytes left to right,
at each position test the markers in corpus order, take the first that matches,
emit one count, advance past the matched span; on no match advance one byte
(`corpus.py:80–92`). A repeated marker counts once per occurrence; overlapping
candidates resolve to the first in corpus order. Two vectors
(`refuse-three-markers`, `refuse-repeated-marker-occurrence-count`) pin it.

This is depth of the highest-leverage kind, and it is the frame's own thesis
enacted: **a different-author witness made the fact more re-derivable.** The same
verdict -- a marker count -- became reproducible across implementations where before
it was reproducible only by accident of shared code. No authority was added, no
actuation, no inside position; coverage and re-derivability deepened. It is the
worked instance of why CONTRIBUTING.md calls a second independent implementation
the highest-leverage contribution: it does not just *test* re-derivability, it
*surfaces the gaps* that were hiding in the single author's blind spot -- which is
the coordinate-singularity fact from this essay's opening, applied to the spec
itself.

### The target-scoped write: `refuse` writes `.refused`, never the input (`membrane.py`)

`refuse` (`membrane.py:126`) scans the input, then writes a *new* clean copy to
`path + ".refused"` (`membrane.py:139`) with matched authority claims replaced by
`[REFUSED-IN-BAND-AUTHORITY]` (`corpus.py:16`, `:88`). It is contractually
forbidden to modify the input (SPEC §4) -- and it does not: the write is to a
sibling path, the original bytes are untouched.

This grounds the most-misread gate, [G4](./G4-advisory.md). "Zero
actuation" does **not** mean "EMET performs no write." EMET writes constantly -- to
the anchor store `anchors.json` (`membrane.py`, in `anchor`), the hash-chained log
`membrane_log.jsonl` (in `record`, `membrane.py:72`), the `.refused` copy (in
`refuse`), and, on operator-authorized `reanchor`, the baseline manifest
(`monitor.py`, in `reanchor`). None of those four is *the audited target*. The
gate is **target-scoped**: zero actuation *on the artifact under judgement, of
EMET's own accord*. A contributor who reads "zero actuation" as "no writes
anywhere" will mis-apply G4 -- flagging the log as a violation, or, worse, taking
the overstatement as license to relax the *real* boundary because the literal one
is plainly already broken.

### The named history: two corrected overstatements

This project's discipline includes **correcting its own overclaims**, and two are
on record as named fixes -- both repairs of G4's phrasing:

- `THREAT-MODEL.md` said "EMET performs no action." False as written: it performs
  actions on its private stores. The defensible claim is *no actuation on the
  target*.
- [../rationale/06-aleph.md](../rationale/06-aleph.md) said "Boundary 6 is the
  absence of a write call." False: `membrane.py` and `monitor.py` contain several.
  The precise claim is the absence of a write call *to the target*.

Both are corrected to the scoped form in SPEC §6.6 and §11. This matters to the
depth/width frame for a reason easy to miss: **correcting an overstated boundary to
its true scope is DEPTH, not width.** It makes EMET describe itself *more
honestly* -- sharper spec, disclosed limit, the is-axis exactly (rubric §6, step 3).
Relaxing a boundary's *real content* to admit a convenient feature is the opposite:
that is the seam being crossed. The two look superficially alike -- both "change a
boundary" -- and telling them apart is the single hardest judgement in the whole
rubric. The test: does the change make EMET *describe itself more honestly*
(depth) or *do more to the world of its own accord* (width)? The aleph correction
even *sharpened* the claim -- the near-nothing edge is not "EMET writes nothing"
(false) but "EMET writes nothing *to the thing it judges*" -- which is a stronger,
truer statement of the same boundary.

### The fact, never a permission: `gate` emits REVERTIBLE (`organs.py`)

One more grounding, because it is the sharpest line between is and ought in the
codebase. The `organs` impedance command, `gate` (`organs.py:88`), emits
`REVERTIBLE` / `NOT_REVERTIBLE` (`organs.py:97`, `:100`) -- the re-derivable *fact*
that a clean operator revert path exists. It is explicitly **not** a permission to
act (SPEC §2; `verdict.py:55`). `REVERTIBLE` says *a revert is possible*; it does
not say *revert*, and EMET does not revert. This is the is/ought seam welded into a
single token: the existence of a clean path is an is-fact EMET may report; the
decision to take it is an ought EMET refuses to author. A change that turned
`REVERTIBLE` into an auto-revert would be the textbook width move -- the fact
acquiring deontic force, the seed growing a *for*.

---

## The symmetric risk: width is one wrong direction, freeze is the other

A frame that warned only against width would be dishonest, and it would fail its
own fidelity standard. **Over-minimalism -- purity-as-uselessness -- is the
symmetric failure, and it is just as real.** The asymmetry between the axes is
*directional*, not a license to refuse all growth: width (ought-axis) is
disqualifying, but refusing *depth* (is-axis) is equally a way of disqualifying
EMET -- along the other axis.

The over-minimalist failures to watch for (the rubric's §5 enumerates them; the
frame-level point is what follows):

- **Verifying only toy fixtures** -- if the vectors and walkthrough exercise only
  crafted inputs, "re-derivable" becomes a claim about a sandbox, not the world.
  Coverage on real, adversarial targets is *required* depth.
- **Indefinitely deferring the machine interface** -- the JSON envelope and the
  v1.1 exit-code split are DEPTH; treating them as forever-deferred "later
  deliverables" in the name of minimalism refuses the is-axis growth the project
  needs.
- **Doc-mass exceeding the core** -- when the rationale and process documents
  substantially outweigh the verifier, the project has begun optimizing for the
  description over the thing. *(This essay is subject to that caution. It earns its
  place only by making the frame operable below the one-page rubric -- grounding it
  in code and history the rubric has no room for. If it grew past that, it would
  be over-minimalism's other face.)*

The load-bearing point: **the rubric governs the SEAM, not a freeze.** A
maintainer who blocks a JSON envelope, a coverage expansion, or a second
implementation "to stay minimal" has mistaken the freeze for the seam, and is
disqualifying EMET along the is-axis the way creep disqualifies it along the
ought-axis. "Refuse every change" is not the discipline; it is the over-minimalist
failure wearing the discipline's clothes. Both axes have a wrong direction. The
frame names both, and a depth/width essay that named only the width direction
would itself be the over-minimalist error -- it would have refused the is-axis
content (the genuine upside) that makes the discipline a seam rather than a wall.

---

## The strongest objection, and the answer

> **Objection.** The is/ought, depth/width distinction is doing no real work; it
> is a rhetorical relabeling of "features I like" versus "features I don't." Every
> real engineering decision is a tradeoff. You *say* the two axes don't net, but
> that is just a refusal to do the cost-benefit analysis that all engineering
> requires. A signing capability would let CI trust EMET's output; a block-on-DRIFT
> mode would stop a bad deploy; a risk score would let a dashboard rank artifacts.
> These are *useful*. Calling them "ought-axis" and declaring them categorically
> off-limits is not a principle -- it is a way of winning an argument by definition,
> immunizing a design choice from the tradeoff reasoning every other tool submits
> to. If "useful but disqualifying" is coherent at all, name the cost in the same
> units as the benefit, or admit there is no cost and you just prefer the
> minimal shape.

This is the right objection -- it is the *triviality / definitional-immunity* worry
any axis-talk must survive: if the axes are just a relabeling, the distinction
discriminates nothing and the frame dies of triviality. The answer is that the
two axes are **not** a relabeling, because the ought-axis cost is nameable in
units that are categorically not the is-axis benefit's units -- and the way to show
it is to do exactly what the objection demands: name the cost.

Take the objection's three examples and name each cost precisely.

- **Signing** (held key, [G1](./G1-re-derivable.md)). Benefit, is-axis: CI gets a
  cryptographic attestation it can check. Cost, ought-axis: the verdict now rests
  on a key the maintainer *holds*, so an independent re-implementation can no
  longer reproduce the verdict from bytes alone (SPEC §6.5, §8). The cost is not
  "slightly less re-derivable." It is *re-derivability gone* -- the one assurance
  EMET offers, replaced by a property the tool has. You cannot net "CI convenience"
  against "the tool stopped being re-derivable," because the second is the
  precondition of the first having any meaning: a signed verdict from a
  non-re-derivable tool is a signed assertion of authority, the exact thing
  Boundary 1 forbids. (Signing in a *separate adapter package* that signs the
  *governed tokens* is fine -- that is depth via G5; signing *welded into the core*
  is the breach. The seam is real and locatable.)

- **Block-on-DRIFT** (enforcement, [G4](./G4-advisory.md)). Benefit,
  is-axis: a bad deploy is stopped. Cost, ought-axis: a `DRIFT` now *does
  something* of EMET's own accord -- advice has become enforcement, the verdict has
  acquired deontic force it was never entitled to
  ([../rationale/06-aleph.md](../rationale/06-aleph.md), Boundary 4). And here the
  objection's own framing defeats it: the deploy can *already* be stopped, by the
  operator, because the exit code is the integration point -- a CI step can choose
  to fail on exit 2. That is the operator acting on a fact, which is correct. EMET
  blocking *of its own accord* adds no capability the operator lacks; it only moves
  the authorship of the *ought* from the operator into the tool. The benefit is
  fully available on the is-axis; only the *authorship* moves to the ought-axis,
  and that move is all cost.

- **Risk score** (authority, [G2](./G2-closed-lattice.md)). Benefit, is-axis: a
  dashboard ranks artifacts. Cost, ought-axis: a 0–100 number presented as a
  verdict is a graded trust assertion -- `TRUSTED` with a decimal point. Facts do
  not come in degrees of permission. The honest expression of "how changed" is the
  *set* of `DRIFT` results and their hashes, which a dashboard can rank perfectly
  well -- the is-axis benefit survives without the manufactured scalar. What the
  score adds over the hash set is exactly the authority claim, which is exactly the
  cost.

In every case the pattern holds: **the is-axis benefit is recoverable on the
is-axis** (a separate adapter, an exit code, a set of hashes), **and what the
ought-axis version adds over that is exactly and only the disqualifying
capability.** That is the proof that the axes do not net, stated in the
objection's own units: subtract the recoverable is-axis benefit from the proposed
feature, and the remainder is pure ought-axis cost with no is-axis residue. The
distinction is therefore not definitional immunity; it is a *decomposition* -- and
a decomposition that always leaves a pure-authority remainder is doing real work,
because it tells you precisely which is-axis-shaped feature to build instead.

So the objection lands on a strawman ("declared off-limits by fiat") and misses
the structure ("decomposed, and the is-axis part is always buildable separately").
The frame does not refuse the tradeoff. It does the tradeoff and discovers, every
time, that the useful part has an is-axis home and the disqualifying part is an
indivisible category error -- which is what "useful but disqualifying" means,
precisely and non-trivially.

---

## Refuter

A frame worth keeping must say how it would fail. This one fails if either
half of the asymmetry is shown to be hollow.

> **Refuter A (the asymmetry is decorative).** Exhibit an ought-axis feature whose
> disqualifying part *cannot* be decomposed away -- a useful capability that
> requires authority, adjudication, inside-position, enforcement, a held key, or
> target actuation, **and** whose is-axis benefit is *not* recoverable by any
> separate adapter, exit code, or richer fact set. If such a feature exists, then
> "the useful part always has an is-axis home" is false, the two axes genuinely
> net, and the asymmetry is a tradeoff after all -- to be weighed, not gated.
>
> **Refuter B (the gate is over-tight).** Exhibit an is-axis change -- a deeper
> corpus, a coverage expansion, a machine envelope, a second implementation -- that
> a maintainer blocked *as if* it were width, and show that blocking it left EMET
> categorically unchanged in the safe direction while disqualifying it along the
> is-axis (the over-minimalist freeze). This does not refute the width half; it
> refutes any *application* of the frame that mistakes depth for width.

Both refuters are real and contentful. Refuter A is the wager that the
decomposition in the previous section *always* succeeds: every ought-axis feature
splits into a buildable is-axis part plus an indivisible authority remainder. A
single counterexample -- one useful capability with no is-axis home -- sinks it.
Refuter B keeps the frame honest in the other direction: it is satisfied every
time someone freezes the project in minimalism's name, and its existence is why
the symmetric-risk section is not optional. The frame earns its keep only so long
as both stay un-triggered -- checkable, feature by feature, against SPEC §6 and the
governed set, by anyone, with no appeal to the authority of this document. (A frame
that had to be *believed* rather than *checked* would be the very in-band authority
EMET's `refuse` exists to strip -- so this essay, like the curation it sits beside,
claims no authority of its own; its standing is whatever its argument earns,
re-derived, not asserted.)

---

## Where this sits

This essay is the central frame the six gates operationalize. Read the gates for
the per-boundary litmus, each grounded in its own SPEC §6 clause and its own code:

- [G1 -- Re-derivable: no secret, no held key, no clock](./G1-re-derivable.md)
- [G2 -- Stays in the closed lattice](./G2-closed-lattice.md)
- [G3 -- Outside the audited system](./G3-outside.md)
- [G4 -- Advisory: zero actuation on the target](./G4-advisory.md)
- [G5 -- Named-core stays stdlib-only](./G5-minimal-core.md)
- [G6 -- Takes no model-safety or content decision as input](./G6-no-adjudication.md)

The spine is [./README.md](./README.md); the one-page litmus that runs this frame
gate-by-gate is [../scope-discipline.md](../scope-discipline.md).

---

*Further reading (lineage and grounding, never warrant): [SPEC.md](../../SPEC.md)
§§2, 6, 8, 11, 12, 13, 14, 16; [CONTRIBUTING.md](../../CONTRIBUTING.md) (the
non-negotiable boundaries; "fix the spec, not the code"; a second implementation
as highest-leverage); [THREAT-MODEL.md](../../THREAT-MODEL.md) (the "performs no
action" phrasing corrected for G4). Code cited:
[`verdict.py`](../../verdict.py) (`governed()`, the `FORBIDDEN` set, the per-channel
frozensets), [`corpus.py`](../../corpus.py) (`scan`, the non-overlapping-leftmost
rule), [`membrane.py`](../../membrane.py) (`refuse` writing `.refused`; the private
writes in `anchor`, `record`), [`organs.py`](../../organs.py) (`gate` emitting
`REVERTIBLE` as a fact, not a permission), [`monitor.py`](../../monitor.py)
(`report`, `reanchor`). Rationale siblings:
[../rationale/04-spoken-for.md](../rationale/04-spoken-for.md) (L2/L3,
direction-neutral generativity),
[../rationale/06-aleph.md](../rationale/06-aleph.md) (the emet/met aleph, the
boundaries as one closed edge),
[../rationale/01-is-ought-seam.md](../rationale/01-is-ought-seam.md) (the seam this
frame applies to the roadmap),
[../rationale/00-orientation.md](../rationale/00-orientation.md) (the five frames;
the authored stop, L14).*

# The Symmetric Risk: Over-minimalism

> **Status of this document.** This is one essay in the scope-discipline
> curation ([README.md](./README.md) is the spine; the one-page litmus is
> [../scope-discipline.md](../scope-discipline.md)). It binds nothing by its own
> assertion. Every claim below is offered to be re-derived from a
> [SPEC.md](../../SPEC.md) §6 boundary, the [CONTRIBUTING.md](../../CONTRIBUTING.md)
> non-negotiables, and EMET's own code and history; where it points to the
> `research/` lineage or the rationale curation, it points as *further reading*,
> never as warrant. A SPEC-only reader should be able to follow the whole of it.
> If this essay and `SPEC.md` ever disagree, `SPEC.md` governs and this essay is
> wrong.

The unifying fact the whole of EMET encodes is that **integrity is witnessed,
not self-attested**: nothing can be its own independent witness. A compromised
substrate re-derives a compromised self-hash and reports itself intact
(SPEC §11, trust-root regress); a same-author second port agrees with its own
authors' misreading (SPEC §12, why the Rust, Node.js, and Go implementations do not
yet satisfy the bar); one coordinate chart always leaves a singularity it cannot
see. The scope-discipline rubric is the governance layer that keeps EMET the
kind of artifact that can carry that fact. It governs what EMET may *become*:
EMET may grow without bound on the **is-axis** (DEPTH -- more re-derivable, more
covered, better specified, better evidenced) and is disqualified by any growth on
the **ought-axis** (WIDTH -- authority, adjudication, inside position, enforcement,
a held key, actuation on the target). The sibling rubric ([G2-closed-lattice.md](./G2-closed-lattice.md)
and the other gate essays) develops each gate against creep -- growth on the
ought-axis. This essay develops the other edge.

Because scope discipline is a seam, it has a wrong direction on *both* sides.
The gate essays guard against the ought-axis. **This one guards against an
is-axis that never gets built** -- purity held so tightly that the verifier
verifies nothing anyone runs in anger. The rubric's own §5 names this the
symmetric risk and calls it over-minimalism, purity-as-uselessness. The one-page
statement is correct but compressed. This essay earns its place only by going
deeper than that: by grounding the failure in EMET's actual code and this
project's real history, by developing the strongest objection and answering it,
by marking which mappings are load-bearing and which merely illuminate, and -- the
hardest part, and the one the topic demands -- by turning the caution honestly on
*this curation itself*. If what follows only restates §5, it is bloat, which is
the exact over-minimalism failure it describes. So it stops the moment it returns
nothing new.

---

## 1. Why the risk is symmetric, not a footnote

The creep gates and the over-minimalism caution are not two unequal things -- a
real boundary and a hedge against it. They are the two faces of one seam, and the
seam is the is/ought distinction applied to EMET's own roadmap rather than to a
signal arriving at a boundary (the same seam the rationale curation turns on:
[../rationale/01-is-ought-seam.md](../rationale/01-is-ought-seam.md)).

Set it out as a single asymmetric figure. EMET sits at a point on the seam: it
does the authentication-grade is-decision (does the byte re-derive -- `MATCH` /
`DRIFT` / `UNVERIFIABLE`) and refuses the authorization-grade ought-decision
(*may this authentic signal cross?*). Two failures move it off that point:

- **Creep** moves EMET *across* the seam onto the ought-axis. It acquires
  standing it must never hold -- it emits a `TRUSTED`, runs inside the target,
  blocks of its own accord. The gate essays catch this. A creep failure makes
  EMET *do more to the world*.
- **Over-minimalism** keeps EMET *on the right side of the seam but starves the
  is-axis* -- refuses the depth that would make the is-decision cover real
  artifacts, be consumable by real machines, be re-derived by a real second
  author. An over-minimalist failure makes EMET *describe and verify less of the
  world*, until what it verifies is a sandbox, not anything that matters.

The figure makes the symmetry exact and shows why over-minimalism is not a
softer worry. **Both failures disqualify EMET -- they just disqualify it on
different axes.** Creep disqualifies it as a *witness* (an authority is not a
witness; it is a party). Over-minimalism disqualifies it as a *useful* witness (a
witness to nothing anyone needs witnessed is no one's witness). The unifying
thesis -- integrity is witnessed, not self-attested -- needs *both* clauses to
survive: EMET must stay a witness (creep gates) *and* must actually witness
something (this essay). A pure verifier that never verifies a real thing has kept
its non-attestation by attesting to nothing -- it has won the wrong half of its
own thesis.

> **Mapping status -- load-bearing.** The claim "both axes have a wrong
> direction" is not decoration; it is the load-bearing reason a maintainer may
> *not* treat "refuse everything" as the safe default. If only creep were a
> failure, the dominant strategy would be to ship nothing, and that strategy is
> precisely what §1 here rules out. The asymmetry (creep crosses the seam,
> over-minimalism starves an axis) is what makes the two failures
> *distinguishable* on a concrete diff -- see §6.

---

## 2. The four over-minimalist failures, grounded in this repository

§5 of the rubric names the failures. The deepening this essay owes is to ground
each one in code and in this project's real state, not to restate the list. Each
of the following is checked against the repository as it actually stands.

### 2.1 Verifying only toy fixtures

The over-minimalist version of coverage is a conformance suite that exercises only
crafted inputs. EMET's worked walkthrough fixture
(`docs/rationale/walkthrough/input.txt`) is exactly such a crafted target: benign
lines salted with public marker signatures so `refuse` returns a known
`in_band_authority_claims=` count and `verify` returns `MATCH` on bytes the
harness itself anchored a moment earlier. That is correct *as a walkthrough* -- a
deterministic, re-derivable teaching transcript needs a fixed input. The failure
is not having it; the failure is *stopping there*.

The honest reading of the repository's current state: the 35 conformance vectors
(`conformance/vectors.json`, counted by `id` field -- high confidence) and the
walkthrough together pin behavior on **inputs EMET's own authors constructed**.
This is not a flaw to apologize for -- pinned vectors are how an independent
implementation reproduces a verdict at all (SPEC §12), and they are genuine
is-axis depth. But "re-derivable" earns its full meaning only when EMET is also
pointed at artifacts it did *not* author the shape of: a real model weight file, a
real prompt template under a real injection attempt, a real CI artifact whose
bytes drifted for a real reason. SPEC §4's `corroborate` exists precisely to be
run against the messy world -- disjoint read paths over a file that some real
process touched -- and the moment its read-path set is exercised only against
sandbox copies, `QUARANTINE_READ_PATH_DIVERGENCE` becomes a verdict the suite can
*describe* but has never *caught in the wild*.

**The gate this engages, and the direction.** Coverage is is-axis depth (rubric
§1, the coverage bullet). Refusing to expand coverage to real, adversarial targets
"to stay minimal" is not discipline -- it is the over-minimalist failure. Depth on
the coverage axis is *required* growth, not optional. The cure and the failure
share a shape: both add inputs; only one adds inputs the authors did not control.

> **Mapping status -- load-bearing.** That toy-only verification makes
> "re-derivable" a claim about a sandbox is not an analogy; it is the literal
> consequence of the witness thesis. A fixture EMET's authors shaped is, with
> respect to *those authors*, not an independent witness -- it agrees with the
> hand that built it, the same way a same-author port agrees with its authors'
> misreading (SPEC §12). Toy-only coverage is the witness failure recurring one
> level up, in the test corpus.

### 2.2 Indefinitely deferring the machine interface

This is the failure the repository is *most exposed to right now*, and saying so
plainly is the point of grounding the essay in real history rather than in the
abstract.

Two is-axis deliverables are named in the spec as targets and are, as of this
writing, **not built**:

- **The machine-readable JSON envelope.** SPEC §13 ends: "A future
  machine-readable JSON envelope (the v1 target) supersedes this grammar for
  programmatic consumers." It does not exist in the core. `membrane.py` imports
  `json` (line 40) and uses it for the anchor store and the audit log only (lines
  44, 75–93, 199–202); there is no `--json` flag and no envelope command (high
  confidence -- verified by reading the command dispatch and grepping the module).
  A consumer today must scrape pinned stdout tokens (SPEC §13's grammar:
  `MATCH input.txt`, `result=COHERENT`, `in_band_authority_claims=N`).
- **The v1.1 exit-code split.** SPEC §5 names a v1.1 TARGET: split the current
  exit-2 class into exit 1 for `DRIFT` and exit 2 for `UNVERIFIABLE`, so CI can
  tell a *changed* artifact from an *unanchored* one. It is not shipped.
  `membrane.py` returns `exit 2` for every member of that class today -- drift,
  unverifiable, coherence-differs, quarantine, broken chain all collapse to one
  code (lines 94, 110, 118, 124, 131, 137, 159, 188, 192, 205 -- high confidence).

The rubric's own §4 classifies both of these as **DEPTH -- ship them**: each
carries the *same* governed verdicts (`MATCH` / `DRIFT` / `UNVERIFIABLE`) to a
consumer that can read them, adding consumability or resolution to a fact without
adding a new verdict, an authority, an inside position, or an actuation. They pass
all six gates. They are is-axis growth the project *needs*.

The over-minimalist failure is to keep them deferred *as a matter of identity* --
to treat "EMET is minimal" as a reason never to build the interface a machine can
consume cleanly. That reasoning is a category error. Minimality is a property of
the **trusted computing base** (SPEC §10: the named core depends only on the
language and standard library, adds no third-party runtime dependency). The JSON
envelope adds *no dependency* -- `json` is stdlib and already imported. Deferring
it does not protect the TCB; it just leaves the is-axis un-grown. A tool no machine
can consume cleanly is pure in a way that helps no one, and "pure in a way that
helps no one" is the precise definition of the failure this essay is about.

There is a real and legitimate reason these are not yet built: the v1.1 exit split
*requires a migration plus a vector update done together* (SPEC §5;
[CONTRIBUTING.md](../../CONTRIBUTING.md): spec and vectors move as one), and that
is correctly hard, because consumers currently depend on the v1.0 codes being
authoritative. Disciplined sequencing is not over-minimalism. The failure is not
"unbuilt"; the failure is "unbuilt *forever, on principle*." The test that tells
them apart: is there a dated, vector-backed plan to ship it, or is "minimal" being
used as the reason it never ships? The first is discipline. The second is the
freeze wearing the discipline's clothes (§4 below).

> **Mapping status -- load-bearing.** The envelope-and-exit-split case is the
> single most concrete instance of the symmetric risk in this repository, and the
> claim "minimality is a TCB property, not an interface property" is the
> load-bearing distinction that defuses the most common rationalization for the
> freeze. It is checkable: read SPEC §10 (what minimal means) against SPEC §13 and
> §5 (what is deferred), and confirm the deferred items add no §10 dependency.

### 2.3 The separate-package escape hatch as a fig leaf

Gate G5 (named-core stays stdlib-only; integrations live in separate packages) is
the rubric's pressure-release valve: an adapter that needs an outside dependency --
SARIF, in-toto, signing, fuzzing -- does not get refused outright; it gets moved
*out of core*. SPEC §10 contemplates exactly this: "Optional adapters … MAY pull
additional dependencies but MUST live in separate packages."

The over-minimalist abuse of that valve is to let "it can always live in a
separate package" become a reason to *never build the useful adapter at all* -- to
treat the escape hatch as a way of saying yes-in-principle while shipping nothing.
The hatch was meant to keep integrations *available* without enlarging the TCB; the
failure turns it into a polite refusal.

**Here the repository tells the honest, and load-bearing, counter-story.** The
escape hatch is *not* a fig leaf in EMET, because the useful adapter was actually
built: `adapters/attest.py` exists. It wraps an EMET verdict as an in-toto v1
Statement so the verdict is consumable by cosign, slsa-verifier, and Sigstore
policy-controller with zero EMET-specific code on their side. It lives outside the
core (its module docstring states "this adapter lives outside the core (SPEC
section 10)"), it is stdlib-only, and -- critically for the witness thesis -- it
**emits unsigned JSON and holds no key**: "EMET holds no key (SPEC boundaries 5
and 6). The OPERATOR signs … EMET attests; the operator actuates." The adapter
takes the escape hatch and *uses* it: it delivers the integration (is-axis depth,
real consumability) without importing anything into the named core (G5 satisfied)
and without acquiring a held key or an actuation (G1, G4 satisfied -- the seam held
on both axes at once).

So the lesson EMET teaches here is the *answer* to the over-minimalist failure,
not an instance of it: the separate-package pattern is vindicated *by being
exercised*. The caution still stands -- the *next* adapter (a SARIF emitter, say)
could be indefinitely deferred with "it can live outside core" as the excuse -- but
the precedent is set in the right direction. The fig-leaf failure is the one EMET
has so far *avoided*, and the way it avoided it (build the adapter, out of core,
key-free) is the template.

> **Mapping status -- load-bearing (as a positive instance).** That
> `adapters/attest.py` exists, is out-of-core, and holds no key is direct
> evidence that the escape hatch can be used rather than hidden behind -- it is the
> empirical refutation of the claim that G5 is a polite way to say never. The
> mapping is load-bearing because the *manner* of the adapter (key-free, operator
> signs) is exactly the seam: depth delivered on the is-axis, nothing acquired on
> the ought-axis.

### 2.4 Doc-mass exceeding the core -- and the self-turn

The fourth failure is the sharpest, because to state it honestly is to indict the
document stating it. When the rationale and process documents substantially
outweigh the verifier they describe, the project has begun optimizing for the
description over the thing.

Here are the numbers from this repository, and they are not close (all line counts
high confidence, measured directly):

- **The named core** -- `membrane.py` (224), `monitor.py` (97), `corpus.py` (96),
  `organs.py` (113), `verdict.py` (104) -- totals **634 lines**. This is the
  "roughly 600-line tool" the curation describes.
- **The rationale curation alone** -- the nine derivation essays (00-08) plus primer,
  index, and glossary under `docs/rationale/` -- totals roughly **3,500 lines**,
  before counting the one-page rubric (`docs/scope-discipline.md`, 488 lines), the
  spine (`RATIONALE.md`, 128), the design specs, or this essay.

**Doc-mass already exceeds the core by a multiple of five or more.** The condition
§5 warns about is not a future risk for this project; it is the present tense. The
caution must therefore be turned, without flinching, on the curation itself --
*including this very essay*. A large dissertation layer about a 600-line tool *is*
exactly the failure the rubric names. There is no reading on which the essay you
are reading escapes its own indictment by writing more.

What, then, justifies any of it? Only one thing, and it is the same standard the
prose itself must meet: **doc-mass earns its place exactly insofar as it makes the
tool more re-derivable by a second author, and is bloat exactly insofar as it does
not.** SPEC §12 sets the project's actual open deliverable: an *independent,
different-author* implementation passing the conformance vectors. The Rust,
Node.js, and Go ports are clean-room but same-author (README §Status), so they demonstrate
the spec is *implementable*, not that it is *independently re-derivable* -- the
witness thesis, applied to the implementations. Documentation that lets a stranger
re-derive EMET from the spec alone -- that turns "you'd have to read the code" into
"the argument is on the page" -- is is-axis depth: it is *coverage and evidence* in
the rubric's §1 sense. Documentation that merely re-asserts, in more words, what
`SPEC.md` already says normatively is doc-mass with no re-derivability payload, and
it is the over-minimalist failure's other face -- optimizing the description over
the thing.

This gives a hard, checkable test for the curation, and for this paragraph:
**would a different-author re-implementer be helped by this text, or only an
admirer of it?** The rubric's own §5 anticipates exactly this self-application:
"This document is itself subject to that caution: it earns its place only by
making the gates *operable*, and if it grows past that it is over-minimalism's
other face." The same sentence is true of every essay in this curation, this one
loudest of all. The discipline (L14 of the curation's own conventions: a section
ends when it returns nothing new) is the mechanism. It is why this essay is
stopping soon.

> **Mapping status -- load-bearing, and self-applied.** The 634-vs-~3,500 ratio is
> not an illustration; it is the empirical fact that makes the self-indictment
> binding rather than rhetorical. The essay does not get to name doc-mass as a
> failure and exempt itself. Its only defense is the re-derivability payload
> test, which it must pass paragraph by paragraph or be cut.

---

## 3. The strongest objection, and the answer

> **Objection.** "Over-minimalism is not a real symmetric risk. It is a
> rhetorical hedge -- a way to make the discipline sound balanced. The two sides
> are not equal. Creep is irreversible and catastrophic: once EMET ships a
> `TRUSTED`, downstream consumers depend on it, and you can never claw the
> authority back without breaking them -- the seam is crossed permanently.
> Over-minimalism is merely a missed opportunity: an unbuilt JSON envelope can be
> built next quarter; nothing is lost, nothing is corrupted. A risk you can fix at
> any time by simply doing the work is not a risk in the same sense as a risk that,
> once realized, cannot be undone. So the rubric should be *asymmetric on purpose*:
> refuse aggressively, ship conservatively, and treat the over-minimalism section
> as a courtesy, not a constraint."

This is the strongest objection because its premise is *true*: creep and
over-minimalism are not symmetric in *reversibility*. Crossing the seam is
sticky; an unbuilt feature is not. Conceding that fully is the only honest start.

The answer is that the objection equivocates on "risk" and, in doing so, smuggles
in the very failure it claims is harmless.

**First, the harm of over-minimalism is not "a missed feature" -- it is a false
claim.** The unifying thesis is that integrity is *witnessed*. A verifier that has
only ever verified fixtures its own authors crafted, that no machine can consume
cleanly, that no different-author implementation has re-derived, is making a
re-derivability claim its actual practice does not support. SPEC §12 is explicit
that re-derivability is *not demonstrated* until an independent implementation
exists, and the README states this plainly rather than papering over it ("an
inflated claim would refute itself"). Over-minimalism does not leave the claim
un-grown; it leaves the project *asserting* re-derivability while declining to do
the work that would witness it. That is not a missed opportunity. It is the
self-attestation failure -- the exact thing EMET exists to refuse -- reappearing as
the project's own posture. "We are re-derivable, trust us, we just never let anyone
re-derive us" is `TRUSTED` spoken about the project instead of emitted by the tool.

**Second, "fixable at any time" is the rationalization, not the rebuttal.** Every
indefinitely-deferred deliverable is, at every instant, "fixable next quarter."
That is *why* the failure is insidious: it never presents as a crisis, so it is
never prioritized, so the JSON envelope and the v1.1 split sit in SPEC §13 and §5
as "targets" indefinitely (they sit there right now). The reversibility the
objection leans on is the mechanism of the harm, not its absence. A risk that is
always individually deferrable and never collectively undertaken is a risk that is
*realized by default*.

**Third, the asymmetry the objection wants is already in the rubric -- and it is
not the asymmetry the objection draws.** The rubric *is* asymmetric: any single NO
on the six gates is disqualifying, while is-axis growth is unbounded (rubric §1,
§2). Creep is caught at a hard perimeter; depth is encouraged without limit. But
that asymmetry says *ship aggressively on the is-axis and refuse aggressively on
the ought-axis* -- the opposite of "ship conservatively." The objection wants
"refuse aggressively, ship conservatively," which collapses both axes toward the
freeze and is precisely the error §5 names: a maintainer who blocks a JSON
envelope or a coverage expansion "to stay minimal" has mistaken the freeze for the
seam and is disqualifying EMET along the is-axis the way creep disqualifies it
along the ought-axis.

So the concession stands -- the two failures differ in reversibility -- and the
conclusion is rejected. Symmetry was never a claim about reversibility. It is the
claim that *both directions have a wrong way*, that a verifier can fail by becoming
an authority *or* by becoming useless, and that the witness thesis is unsatisfied
in both cases. The objection, by treating over-minimalism as a courtesy, licenses
exactly the indefinite deferral that turns a re-derivability claim into a
re-derivability *assertion* -- and an assertion of re-derivability that no one re-
derives is the failure with EMET's name on it.

---

## 4. The seam, not the freeze: refusing every change is the failure in disguise

The load-bearing operational point -- the one a maintainer carries to a pull
request -- is that **the rubric governs the seam, not a freeze.** Its job is to keep
growth on the is-axis (depth) and off the ought-axis (authority, adjudication,
inside position, enforcement, held key, target actuation). Its job is *not* to stop
growth.

"Refuse every change" is not the discipline. It is the over-minimalist failure
wearing the discipline's clothes. The tell is that the freeze and the discipline
produce *identical behavior on the easy cases* -- both refuse a `TRUSTED`, both
refuse a `--fix` flag -- and *diverge only on the is-axis*, where the discipline
ships and the freeze refuses. A maintainer who blocks a JSON envelope (G2-clean
depth, SPEC §13), a coverage expansion (more real targets, §2.1 above), a new
governed marker (data, not a code branch -- rubric §4), or a second implementation
(the *highest-leverage* contribution there is -- CONTRIBUTING.md) "to stay minimal"
has not been disciplined. They have disqualified EMET along the is-axis the way
creep disqualifies it along the ought-axis.

This is why §6 of the rubric -- *fix the spec, not the code* -- matters to the
over-minimalist failure specifically. When a needed capability fails a gate, the
disciplined response is to ask whether the *spec* has a genuine gap, and if so to
change `SPEC.md` and `conformance/vectors.json` together. The over-minimalist
response is to treat the gate's NO as a final verdict against the capability and
move on. But a gate that genuinely blocks a needed depth is *evidence about the
spec*, not a verdict against the depth. The whole project runs on that posture: the
warrant is the argument and the re-derivation, never the authority of whoever holds
the pen -- which means a maintainer's "no" carries no more authority than its
re-derivable grounding, and "to stay minimal" with no gate behind it is no
grounding at all.

The asymmetry of the perimeter cuts both ways here. A perimeter with one segment
open is open (rubric §2) -- that is the case against creep. But a perimeter that has
been *welded shut around an empty interior* encloses nothing -- that is the case
against the freeze. The gates are six segments of one boundary; the interior they
protect is supposed to *contain a growing, useful, re-derivable verifier*. Guarding
an empty interior perfectly is not a smaller success. It is the failure with a
clean audit log.

---

## 5. The test a maintainer actually runs: telling depth from the freeze

The gate essays give a six-gate litmus for creep. The symmetric risk needs its own
one-line discriminator, because over-minimalism does not fail a gate -- it *passes
all six by doing nothing*, and a perfect gate score is exactly its disguise.

The discriminator, derived from §§1–4:

> A refusal is **discipline** if it is grounded in a specific NO on one of the six
> gates -- a named ought-axis crossing (authority, adjudication, inside position,
> enforcement, held key, target actuation). A refusal is **over-minimalism** if it
> blocks is-axis growth (re-derivability, coverage, evidence, spec rigor,
> consumability) with *no* gate-grounded NO behind it -- if its only warrant is
> "to stay minimal," "that's scope creep" asserted without a gate, or "it can live
> in a separate package" used to mean *never*.

Run it against the four failures:

- **Toy-only coverage** (§2.1): refusing real, adversarial targets has no
  gate-NO behind it -- real targets cross no boundary. Over-minimalism.
- **Deferred machine interface** (§2.2): the JSON envelope passes all six gates
  (rubric §4) and adds no SPEC §10 dependency. Refusing it "to stay minimal" has
  no gate-NO. Over-minimalism. (Disciplined *sequencing* of the v1.1 split behind
  its required vector migration is *not* a refusal and not this failure.)
- **Fig-leaf escape hatch** (§2.3): "it can live in a separate package," used to
  mean the adapter never ships, is G5's *valve* turned into a NO with no boundary
  behind it. Over-minimalism. (EMET avoided this: `adapters/attest.py` shipped.)
- **Doc-mass over core** (§2.4): prose that adds no re-derivability payload has no
  is-axis justification *and* no gate to hide behind. It is bloat by the curation's
  own L14. Over-minimalism, self-applied.

The discriminator is checkable by anyone, against SPEC §6 and the governed set,
with no appeal to the authority of this document -- which is the only kind of test
this project is allowed to offer.

---

## Refuter

A claim worth keeping must say how it would fail. This essay's central claim -- that
over-minimalism is a *real, symmetric* disqualification, not a courtesy -- fails if
either of two things is shown:

> **If every is-axis deferral the essay calls a failure can be shown to leave EMET
> categorically better off un-built -- more re-derivable, more clearly a witness,
> for having *not* shipped the envelope, the coverage, the adapter, the second
> implementation -- then over-minimalism is not a failure mode at all, and §5's
> symmetry claim (and this whole essay) is the hedge the §3 objection accuses it of
> being.** Conversely, **if a refusal this essay labels "over-minimalism" can be
> grounded in a genuine NO on one of the six gates -- a real ought-axis crossing the
> blocked depth would have caused -- then it was discipline after all, the
> discriminator in §5 is miscalibrated, and the essay has cried freeze where the
> seam was actually doing its job.**

Both refuters are actionable and both are checkable without trusting this page. The
first is rebutted concretely by `adapters/attest.py` (a shipped is-axis depth that
left EMET *more* a witness, not less -- out-of-core, key-free) and by SPEC §12's
standing demand for a different-author implementation (an un-built depth whose
absence the project itself names as the gap in its re-derivability claim). The
second is the healthy case: if a depth this essay urges does cross a gate, the gate
governs and the essay is wrong -- `SPEC.md` governs, and the warrant was never this
document. The essay earns its keep only so long as both refuters stay
un-triggered -- and the day it stops earning its keep, the curation's own L14 says
to cut it, which is the discipline this essay exists to describe, applied to
itself.

---

*Further reading (lineage and grounding, never warrant): the spine
[README.md](./README.md) and the one-page litmus [../scope-discipline.md](../scope-discipline.md)
§5 (the symmetric-risk statement this essay deepens), §4 (the DEPTH/CREEP edge
cases), §6 (fix the spec, not the code); the sibling gate essay
[G2-closed-lattice.md](./G2-closed-lattice.md); [SPEC.md](../../SPEC.md) §5 (v1.1
exit split, deferred), §10 (TCB -- what "minimal" governs), §12 (independent
implementation -- the open deliverable), §13 (JSON envelope -- deferred);
[CONTRIBUTING.md](../../CONTRIBUTING.md) (the most valuable contribution; spec and
vectors move together). Code cited: `membrane.py` (the exit-2 collapse, the
json-for-storage-only usage), `verdict.py` (`governed()` -- the structural lattice),
`adapters/attest.py` (the out-of-core, key-free adapter that vindicates G5);
`docs/rationale/walkthrough/input.txt` (the crafted fixture). Rationale siblings:
[../rationale/01-is-ought-seam.md](../rationale/01-is-ought-seam.md).*

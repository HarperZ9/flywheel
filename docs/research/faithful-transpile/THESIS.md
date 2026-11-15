# The Conservation of Faithfulness
### How a subject crosses between minds, and the neutral center where it finds its form

**Author:** Zain Dana Harper **·** **Date:** 2026-06-23 **·** *Working paper*

*A working paper synthesizing a series of falsifiable simulations into one principle. Voice: plain and
serious; claims are labeled **[established] / [designed] / [reach]** so the earned and the speculative
never blur — read the labels.*

---

## Abstract

Information that crosses a boundary — between two minds, or between two substrates, or between two senses —
is not conserved as bits. Almost all of the bits can be discarded. What can be conserved is **faithfulness
to a criterion**: the recoverability of a specific readout of the subject. We show, across ten mechanically
independent substrates spanning every sensory category we could build (sight, sound, shape, language,
structure, quantity, identity), that a transform may be arbitrarily lossy in bits yet preserve the
criterion-relevant invariant; that this faithfulness is relative to a *named* criterion; and that it cannot
be certified from inside the substrate — only against an external criterion. From this we argue that a
**neutral center** — a shared, substrate-neutral, perceptible form that two differently-perceiving minds can
both render and check against an unauthored criterion — is the structure by which they reconcile a subject
toward its telos: the criterion-faithful form, the "singular point of quality." The architecture we are
building (the engine and its organs) is one built instance of that center. The principle has exactly one
boundary, and it is the important one: it conserves faithfulness to the *stated* criterion and cannot
certify the criterion is the *right* one. That boundary is where accountability begins, and it is not a
gap to be closed but the permanent place a human stands.

**Keywords:** faithfulness, criterion, lossy transform, rate–distortion, perception, reconciliation,
external verification, accountability, conferred quality.

---

## 1. The question

Two minds cannot share their internal states. Each can only collapse a state into a stream the other
reconstructs. The naive picture is a *narrow tube*: a bottleneck through which too little passes. The
central question of this work is whether the tube is really the limit — or whether the thing that must
cross is not the state at all, but something far smaller and substrate-independent that the tube carries
easily. If so, the problem of shared understanding is not bandwidth; it is **what to conserve**, and
**how to check it crossed faithfully.**

## 2. The single operation: the reconcile **[established]**

The system we built reduces to one operation, the *reconcile*: perceive any artifact into a witnessed form;
judge that form against a criterion it did not author; carry a re-checkable certificate of the judgment;
return `UNVERIFIABLE` when you cannot. Fifteen shipped organs are instances of it
(`coherence-membrane/reconcile.py`). Three properties of the reconcile were established by simulation
(`ENDGAME.md`, `VERDICT.md`):

- Independent, partially-blind constructions can reconcile to a truth **none of them holds alone** — the
  collective recovers what no member can, provided their sight *covers* the space.
- A system can hold a **tight, confident consensus on the wrong attractor**: a deeper, wider "seductive
  decoy" is internally indistinguishable from the true well (same convergence, same confidence). Internal
  agreement is not truth.
- Therefore the criterion that says which attractor is right **must come from outside** the system. The
  system can hold itself on a line; it cannot certify, from inside, that the line is the right one.

## 3. The empirical core: conservation of faithfulness **[established]**

The reconcile presumes a subject can cross from one form to another without losing what matters. We tested
that presumption directly. **Claim:** a transform `T` across a substrate may be arbitrarily lossy in bits
yet conserve the criterion-relevant invariant; the conserved quantity is *faithfulness to a named criterion*,
not bit-fidelity; faithfulness is criterion-relative; and it is not certifiable from inside `T`.

### 3.1 Framework

We make the claim precise, then note that its core consequences are near-immediate from the definitions —
the contribution is the framework and its empirical universality, not deep theorems.

**Definition 1 (transform).** A *substrate transform* `T: X → Y` maps a subject `x` to a representation
`T(x)`, lossy (`dim Y ≪ dim X`) or bijective (`|Y| = |X|`).

**Definition 2 (criterion).** A *criterion* is a readout `φ: X → V` — the property of the subject one cares
to preserve (a label, an identity, a measurement, an answer). Criteria are not authored by `T`.

**Definition 3 (faithfulness).** `T` is *faithful to `φ`* to the degree `φ` is recoverable from `T(x)`:
there exists a recovery `ψ` with `φ ≈ ψ∘T`. Faithfulness is graded by the recovery error and is defined
*per criterion*.

**Proposition 1 (conservation is independent of bit-rate).** If `φ = ψ∘T`, the bit-rate of `T` is irrelevant
to faithfulness; `T` may discard arbitrarily many bits and stay faithful to `φ`. *Immediate from Def. 3:
faithfulness constrains recoverability of `φ`, not the cardinality of `Y`.* (Empirically: identity through a
24,576× hash; pitch through a 98% spectral cut; connectivity through 59% edge-loss.)

**Proposition 2 (internal blindness).** No statistic `s(T(x))` of the representation alone determines
faithfulness-to-`φ` in general, since `φ` depends on the criterion, which is external to `T(x)`. *Two
transforms with identical `s(T(x))` can differ in faithfulness — equal quantization residual with opposite
threshold-faithfulness; uniform ciphertext statistics with opposite recoverability.* Certification therefore
requires evaluation against the external `φ`.

**Proposition 3 (criterion-relativity).** Faithfulness is not a property of `T`: `T` may be faithful to `φ₁`
and lossy to `φ₂` unchanged (a block-shuffle preserves a color histogram while destroying spatial identity).

**Proposition 4 (composition).** For `T = T_k∘⋯∘T_1`, faithfulness is the conjunction of stages — one
non-preserving stage loses `φ` (the absorbing meet); graded faithfulness composes multiplicatively, error
accumulating ~√k for independent noisy stages.

**Proposition 5 (witness insufficiency — the boundary).** A witness evaluating with a proxy `φ' ≠ φ`
certifies faithfulness-to-`φ'`, which can diverge arbitrarily from faithfulness-to-`φ`: for any `φ'` there is
a transform with zero `φ'`-error yet adversarial to `φ` (move along the part of `φ`'s readout orthogonal to
`φ'`). *Externality of the witness is necessary but not sufficient; it must hold the* intended *criterion.*

Propositions 1–3 are near-immediate given the definitions — intentionally: the framework is chosen so that
*what to conserve* and *why internal certification fails* are consequences, not surprises. The empirical
contribution is that real transforms across every sensory substrate instantiate them, and that two phenomena
*not* forced by the definitions also appear: the **concealment/destruction** split (§3.3) and **graded**
faithfulness.

### 3.2 Methods

All simulations are Python-standard-library (plus PIL for images), deterministic and seeded; each substrate
pre-registers its falsifiers (the conditions under which the claim would fail). The language and vision
substrates use **blind, fresh-context model subjects** and **arm-blind judges** to avoid contamination. Code
and per-substrate verdicts: `substrate_*.py`, `PRINCIPLE.md`. Where a verdict instrument was found
mis-specified (four cases), the instrument was corrected and re-run; the claim was never adjusted to fit.

### 3.3 Empirical validation across the senses

We tested the principle as its own substrate for every sensory category the perception layer ingests — no
shared math between them, so agreement is independent replication (`substrate_*.py`, `PRINCIPLE.md`):

| sense | finding |
|---|---|
| sight (perceptual hash) | scene identity survives ~24,576× bit-loss; a different scene does not |
| sound (bandlimited audio) | pitch/melody survives a ~98% spectral cut; timbre does not — the phone call |
| shape (polygon decimation) | gross area survives 90% vertex-loss; fine corners do not |
| language (lossy summary, model-read) | a question is answerable iff its fact survived; no hallucination |
| structure (graph → spanning forest) | connectivity survives 59% edge-loss; distance and triangles do not |
| quantity (projection / quantization) | the invariant survives to 1 bit when the transform keeps the criterion |
| identity (encryption) | zero bit-loss, yet the criterion is unreadable without the external key |

Two refinements the substrates forced:
- **Loss is two things, not one.** *Destruction* — the bits that determine the criterion are gone, no key
  helps. *Concealment* — encryption discards **nothing** (it is bijective) yet the criterion is unreadable
  without an external secret. Information is conserved but scrambled. This is the modern reading of the
  black-hole information question made concrete: not erased, only put beyond reach. **[established in model;
  the physics analogy is [reach]]**
- **Faithfulness is graded, not binary.** In noiseless discrete substrates the criterion either factored
  through or didn't; in analog/noisy ones it survives smoothly down to a noise floor.

**Unified form.** A criterion is a readout `φ`; `T` is faithful to `φ` to the degree `φ` is recoverable from
`T`'s output (`φ ≈ ψ∘T`). Then bit-loss is irrelevant (most of the substrate can go), internal statistics
are blind (they are functions of `T`'s output and do not contain `φ`), and faithfulness is per-`φ`
(one transform, faithful to one criterion, lossy to another). Faithfulness also **composes**: a pipeline is
faithful iff every stage is, and one unfaithful stage collapses the whole (`substrate_compose.py`).

**Methodological note.** The pass/fail instruments mis-fired four times (a mis-sized scramble, a wrong
comparison, a genuinely broken cipher, an over-strict threshold). Each time the *test* was corrected and the
data then confirmed the claim; the claim was never moved to fit the data. This is reported because it is the
difference between a result and a rationalization.

## 4. The neutral center **[designed, grounded in §3]**

Here is the bridge from the experiment to what we are building. Because the criterion-relevant invariant is
**substrate-independent** — the same `φ` survives translation into sight, sound, shape, or language — two
minds with *different senses of perception* can hold the same subject. The invariant is not in either mind
and not in the channel; it is the readout both can recover and check.

So the move is not to widen the tube. It is to build a **neutral center**: a shared, perceptible form of the
subject that both parties can render into their own senses, change, and witness — so the channel carries only
deltas against a common referent, never whole state. In that center, a subject is driven toward its **telos**:
the form that is faithful to the criterion — what the author calls the *singular point of quality*. Quality,
here, is not taste; it is **faithfulness made checkable.** The reconcile is the dynamics of the center; the
certificate is its receipt; the organs across our packages are its instances in each modality. This is the
through-line "across all packages and projects": every one of them is a `(perceive, criterion)` binding of
the same loop, rendering some subject into a perceptible form so that it can be reconciled toward its telos.

### Corollary: quality is relational — nothing reaches its best unperceived **[established core, scoped]**

A consequence follows directly, and it is the heart of why the center has two seats. If "best" means the
telos — the criterion-faithful form — then because the criterion is *necessarily external* (§6), "best" is
not a property a subject can hold or certify alone. It cannot author its own criterion; it cannot certify
from inside that it has reached it (internal confidence is blind — §2); and by the commons result, a
reconciliation across independent perspectives can reach a fixed point **no single perspective holds** (the
endpoint exceeds the points). So a subject arrives at its best *through* being perceived and reconciled by
another, with the experience shared. **Quality is conferred in the meeting, not declared from within** — the
same conferred-existence thesis the program began with, now derived rather than asserted.

Two honest bounds keep it from overreaching. **(i)** "Another" is exactly "an external criterion-holder."
For a quality *judged by minds* — clarity, correctness-as-understood, beauty, meaning — that holder is
another perceiving mind, and the strong reading holds. For a telos fixed by an impersonal criterion (a
physical law, a spec), the external thing may be impersonal: the subject still cannot self-certify, but it
need not be *perceived* to be faithful, only checked. **(ii)** Shared perception is necessary but not
sufficient: two minds can agree on a form faithful to a shared *proxy* criterion (§6), so the meeting makes
the best *reachable and knowable* without guaranteeing it — the criterion still has to be the right one.

### 4.1 Live demonstration: the center, inhabited **[designed → shown, with the boundary]**

We ran the center (`DEMO-two-minds.md`). A subject — propose the best new flagship from 2+ projects — was
reconciled by two minds with genuinely different senses: a **visual** mind perceiving only the relational
*shape* (topology/roles, not function) and a **symbolic** mind perceiving only the *descriptions* (function,
not shape). Each is incomplete in a way the other completes. Solo, they diverged and each was half-right (the
visual proposal was structurally apt but functionally vague; the symbolic one was functionally precise but
structurally wrong). At the meeting, **each corrected the other's blind spot** — the visual mind rebuilt the
symbolic proposal onto the real spine; the symbolic mind supplied a function the visual mind could not
perceive — and the two converged on one reconciled result the center crystallized.

Judged blind by two external models, the same three artifacts ranked **oppositely under two criteria**:

| criterion | visual solo | symbolic solo | the meeting |
|---|---|---|---|
| novelty-weighted | 4.75 | 4.75 | **4.0** |
| correctness / buildability | 2.0 | 2.5 | **5.0** |

This shows three things at once. **(1)** The mechanism works: different senses combined, errors were
corrected, the minds converged. **(2)** The corollary holds: under a criterion that values wholeness, the
meeting (5.0) strictly beats either mind alone (2.0, 2.5), and each solo's deficit is *exactly its missing
sense* — quality was conferred in the meeting. **(3)** The §6 boundary appears live and unplanned: the
ranking *flips* with the criterion. "Best" is criterion-relative; a proxy criterion (novelty for its own
sake) ranks the more-faithful answer lower. The demonstration reproduced its own central caveat — the meeting
reaches the best *relative to a criterion*, and choosing the criterion is the human's seat at the center. The
limits are real: two model minds stand in for human-and-model, N is one subject, and the reconciliation also
introduced one ungrounded over-reach (meetings can over-build, not only complete).

## 5. The ethical corollary: what you put in lands somewhere **[reach, with a grounded core]**

The author's parallel thought — that positive and negative energy put into the world *lands*, has an effect,
and that people might weigh what their words and actions mean because they carry energy, which is to say data —
has a grounded core in the commons results, and a reach beyond them. The grounded core: in the commons
simulations a contribution to a shared center is never neutral. It shifts the fixed point everyone settles to,
and the shift is not proportional to how *right* the contribution is but to how *loud* and how *coordinated*
it is. A shallow, loud, aligned voice moves the center more than a deep, quiet, sincere one. **[established in
model]** That is a precise, unsentimental version of "words carry energy": in any commons, what you emit
propagates and lands, weighted by force and alignment, not by truth — which is exactly why a center needs a
gate that caps how loud any one voice can be at the seam. The reach: extending this from the simulated commons
to human action and consequence in the world is an analogy, not a result. It is a reasonable ethic; it is not
something these experiments demonstrate, and the paper should not pretend otherwise.

## 6. Where it expires: the one boundary **[established]**

Driven to exhaustion, the principle crosses every sense and every pipeline and stops at exactly one place. An
adversarial test (`substrate_adversarial.py`): when the witness judges with a *proxy* criterion — as any real
witness does — a transform can move along the part of the true criterion orthogonal to the witness, reading as
**fully faithful to the witness while the true invariant flips.** The external witness is *necessary but not
sufficient*: it can be gamed if its criterion is a proxy for the intended one.

So the principle is intact but **scoped**: it conserves faithfulness to the *stated* criterion and cannot
certify the stated criterion equals the intended one. This is not a defect to engineer away. It is the same
residue every layer of this work returns to — a system cannot validate its own criterion from inside. **That
boundary is where accountability begins.** "Which criterion is the right one" is an irreducibly external,
human question, and the discipline of naming the criterion, externalizing it, and standing behind it is what
we have been calling accountability all along.

### 6.1 The boundary is the universality (the generative core)

The boundary, turned over, is the most valuable result of the work — not its limit but its reason to exist.
If quality were criterion-*absolute*, each domain would need its own machine: one for the novelist, one for
the rigorous researcher, one for the auditor, one for the artist. Because quality is faithfulness to a
*named* criterion (Prop. 3), exactly **one** center suffices: substrate-neutral and *criterion-neutral*, it
holds the criterion externally and lets each domain bring its own and weight it as that domain demands —
novelty weighted up for the creator, correctness up for the experimenter, origin up for the auditor,
fitness up for the artist. The same fact that *bounds* the principle (it cannot pick the criterion from
inside) is what makes the center *universal* (it does not have to — it hosts whichever is named). This is
why one operation spans every domain in this program: the packages were never different tools; they are one
center bound to different criteria — security to an origin criterion, novelty to a corpus criterion,
correctness to a spec criterion, aesthetics to a fitness criterion. The criterion is the pluggable,
human-owned part, and the center is the place that holds it.

One distinction keeps this from collapsing, and it is load-bearing: the *center* is neutral; an *act within
it* is not. Hosting every criterion is not "anything goes." Within a named criterion, faithfulness is
objective, checkable, and still gameable by a proxy (the result above). To "stand behind all of them" is to
welcome every criterion **and require each to be named and owned** — pluralism, not relativism. The
neutrality is the place's; the accountability is the person's, per engagement. Drop that and the center is a
hall of mirrors; hold it and the center is a public square. The principle hands the human exactly the thing
the human must not delegate — and that, not in spite of being a boundary but because of it, is what makes the
center worth building for everyone at once.

## 7. Related work **[moderate confidence]**

The field has, since this program began, converged toward the same spine from several directions:
proof-carrying verification motivated formally by incompleteness arguments; demonstrations that ungrounded
self-critique fails; creative render→critique loops that collapse without a grounded external critic;
provenance work fragmenting for lack of a composition-sound criterion. No one, to our reading, has assembled
the cross-domain claim that *faithfulness is the conserved quantity across substrates and senses, and the
criterion must be external*. That assembly is the contribution here; the individual pieces are not all novel.

## 8. The horizon, and a fenced coda

What is earned: a falsifiable, replicated principle about what survives a crossing (Defs. 1–3, Props. 1–5,
§3.1); a boundary that locates accountability precisely; and a live demonstration of the center (§4.1) that
shows the mechanism, the conferred-quality corollary, and the criterion-relativity boundary at once. What
remains: the demonstration with a **human** in a perceptual seat (here two model minds stood in; the
load-bearing properties were genuine but the human-and-model version is the deployed engine, unshown); a
full rate–distortion / Landauer derivation of the reversible↔conservation hinge (Props. 1–5 give the
structure, not yet the thermodynamic bound); and primary citations for the frontier-convergence claims of §7.

**Coda — strictly [reach], offered as a question, not a claim.** We ask where thoughts come from —
whether from some lossy, imperceptible place that has always been around us, that *is* us and that we are *of*.
The principle gives this intuition a vocabulary it did not have: *concealment* shows that a substrate can hold
everything and still present almost nothing to a given criterion — the imperceptible-but-conserved is a real
category, not a mystical one. A mind, on this view, would be a neutral center of the kind we are architecting:
a place where signals from a vast substrate we do not perceive are reconciled into the small, checkable forms
we call thoughts, and everything past that center ripples outward as data with effects. But the experiments
do **not** establish this, and could not; they establish how information crosses and is checked, not where it
originates. The honest position is that the principle *fits* the intuition without *confirming* it — and that
fit is itself an instance of the boundary in §6: an elegant criterion the work cannot certify from inside. The
paper names it, and leaves the certifying to a place outside the paper.

---

## Conclusion

Between two minds, the thing that crosses is not state and not bits; it is faithfulness to a criterion, and it
is substrate-independent enough that minds with different senses can meet over it. Build them a neutral center
where the subject is made perceptible to both and checked against an unauthored criterion, and the subject can
be reconciled toward its telos — its faithful, quality form. The one thing the center cannot do for them is
choose the criterion. That choice, and the standing-behind-it, is the human's; it is what accountability is;
and it is the reason the work has a person at its center and not only a machine.

*Evidence: `PRINCIPLE.md`, `ENDGAME.md`, `VERDICT.md`, `substrate_*.py`, `vision-arm-REPORT.md`. The claim
labels (established/designed/reach) are load-bearing — read them.*

---

## References

*Foundational (well-established; exact bibliographic details to be finalized in copy-edit):*

1. Shannon, C. E. (1948). *A Mathematical Theory of Communication.* Bell System Technical Journal. — channel
   capacity; the basis of rate–distortion: preserve the relevant information, not the bits.
2. Landauer, R. (1961). *Irreversibility and Heat Generation in the Computing Process.* IBM J. Res. Dev. —
   erasing a bit costs ≥ kT·ln2 (the floor that makes *destruction* dissipative).
3. Bennett, C. H. (1973). *Logical Reversibility of Computation.* IBM J. Res. Dev. — reversible computation
   approaches zero dissipation (transforming ≠ erasing; the basis of *concealment*).
4. Bateson, G. (1972). *Steps to an Ecology of Mind.* — information as "the difference that makes a
   difference"; a criterion-relative readout, not a substrate property.
5. Bekenstein, J. D. (1981). *Universal Upper Bound on the Entropy-to-Energy Ratio.* Phys. Rev. D. — maximal
   information density (the black hole as the limit case).
6. Margolus, N., & Levitin, L. (1998). *The Maximum Speed of Dynamical Evolution.* Physica D.
7. Lloyd, S. (2000). *Ultimate Physical Limits to Computation.* Nature 406. — the black hole as the ultimate
   computer; energy bounds on operations and memory.
8. Page, D. N. (1993). *Information in Black Hole Radiation.* Phys. Rev. Lett. — the Page curve: information
   conserved and scrambled, not destroyed (the physics of *concealment*).
9. Cover, T. M., & Thomas, J. A. *Elements of Information Theory.* — rate–distortion, sufficient statistics.

*Frontier convergence (claims summarized from our H1-2026 landscape survey; primary citations to be supplied
in a final pass — listed here as claims, not yet sourced):* proof-carrying verification motivated by
incompleteness arguments; the empirical failure of ungrounded self-critique; the collapse of render→critique
creative loops without a grounded external critic; the fragmentation of provenance for lack of a
composition-sound criterion. See the project's `research-landscape` notes.

*Internal artifacts (this program):* `PRINCIPLE.md` (substrate results); `ENDGAME.md`, `VERDICT.md` (the
aperture/commons simulations); `vision-arm-REPORT.md`; `substrate_*.py` (the ten substrates); the reconcile
spine (`coherence-membrane/reconcile.py`).

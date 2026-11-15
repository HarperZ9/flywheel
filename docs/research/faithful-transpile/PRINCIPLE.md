# Faithful Transpile — a conservation principle for information crossing a substrate

> Status: **driven to natural expiration.** Holds across every sensor category the perception layer
> ingests — sight, sound, shape, language, structure, quantity, identity (10 substrates, no shared
> math) — plus the pipeline (composition) and a unifying formal statement, with two substrate-forced
> refinements (concealment vs destruction; graded faithfulness). Its one boundary is located and named:
> faithfulness is to the *stated* criterion; certifying the criterion is right is the irreducible
> external residue (where accountability begins). Robust by independent replication, falsifiers
> untriggered — **not a theorem.** Readable; Working paper.

## The idea, plainly

A black hole is the densest information store and, by Lloyd's limits, the most efficient computer
physics allows. Storing or computing has a floor cost (Landauer: erasing a bit dissipates ≥ kT·ln2).
This is why a full-fidelity simulation of anything as rich as the world is energetically hopeless —
you'd need a system at least as complex as the thing.

But there is a move the floor-cost argument misses. **Erasing** information costs energy; **transforming**
it need not. A reversible transform can, in the limit, move information into a wholly different form
without dissipating it — nothing is destroyed, only rearranged. The apparent "loss" when you can no
longer read it is not erasure; it is **scrambling** — the information is conserved but moved to where
you can't perceive it. This is, strikingly, the modern reading of the black-hole information paradox:
unitarity holds, information survives, it is merely scrambled beyond practical decoding.

So the question for anything that carries information across a boundary — a tube, a synapse, an engine,
a rendered shape, a token stream — is not *how many bits survive* but *does the thing that matters
survive*. The claim is that it can, even when almost all the bits do not.

## The principle (falsifiable)

> A transform across a substrate may be arbitrarily **lossy in bits** yet **conserve the
> criterion-relevant invariant**. The conserved quantity is **faithfulness to a named criterion**, not
> bit-fidelity. Faithfulness is **relative to that criterion** — a transform can be faithful to one and
> lossy to another at once. And faithfulness is **not certifiable from inside the substrate**: internal
> confidence (tightness, energy retained, agreement) is blind to it; only an **external witness** can
> certify whether the invariant survived.

**What breaks it:** (a) invariant-survival always tracking bit-loss → "lossy but faithful" is
impossible; (b) an internal statistic reliably predicting faithfulness → no external witness needed.

## Evidence so far

**The reconcile arc (`ENDGAME.md`, `VERDICT.md`).** Across the aperture/commons simulations the same
shape recurred: a system can hold a tight, confident consensus on the *wrong* attractor (A4 — the
seductive decoy was internally indistinguishable from truth); the criterion that says which is right
must come from outside the tube. That is this principle's clause (3), found independently.

**It now holds across every sensor category the perception layer ingests — each sense tested as its own
substrate (no shared math), plus structural tests of the pipeline and the witness itself. Perception is
not only sight; the principle is about everything that crosses the layer.**

| sense / category | substrate(s) | transform / loss | result |
|---|---|---|---|
| **sight** — image | perceptual hash + vision arm | image→64-bit, ~24,576× | identity drift 0.004 vs different-scene 0.484; salience-faithful render preserved synthesis, misleading one leaked |
| **sound** — hearing | sound + analog filter | bandlimit, ~98% harmonic energy cut | pitch survives 4/4 notes, timbre ~2% kept — the phone-call: words/melody through, fidelity gone |
| **shape** — geometry | geometry | polygon → 10% of vertices | gross area survives (blob 6%, circle 4% err); 83% of fine corners destroyed |
| **language** — text/meaning | semantic (blind subagents) | summary, ~½ facts dropped | a question is answerable **iff** its fact survived; two summaries faithful to disjoint question-sets; zero hallucination |
| **structure** — relational | graph → spanning forest | 59% of edges dropped | connectivity **1.000**; distance 0.726; triangle 0.492 (same transform, three fates) |
| **quantity** — numeric/data | linear projection + quantization | R⁴⁸→R⁶ 8× / continuous→1 bit | faithful 1.00 vs unfaithful 0.46 at equal bits; aligned 1.000 vs misaligned 0.754 |
| **identity** — provenance/bytes | encryption | bijective, **0 bit-loss** | φ ≈ chance from ciphertext (0.510), external key recovers 1.000; *concealment* vs *destruction* |

This maps onto the sensory-transform-algebra planes — **Field** (sound · analog · image), **Geometry**
(shape), **Graph** (structure) — every plane, plus language and provenance. Every row is the principle,
not analogy: the invariant survives near-total loss when the transform preserves the criterion's structure,
dies at the *same* budget when it doesn't, a within-substrate statistic can't tell which, and faithfulness
is always relative to a named criterion.

**Structural tests (not a sense — the pipeline and the witness themselves):**
- **Composition** (`substrate_compose.py`): faithfulness survives a *pipeline* — faithful-but-noisy chains
  degrade gracefully (~√L), and **one unfaithful stage collapses the whole** (0.955 → 0.501). The engine's
  chain is faithful iff every stage is — the absorbing meet, again.
- **The witness itself** (`substrate_adversarial.py`): the natural boundary — see "Where it expires" below.

**Two refinements the substrates forced (the principle got sharper, not weaker):**
- **Loss splits into *concealment* vs *destruction* (encryption).** Encryption is **zero bit-loss** yet the
  criterion is unreadable without the external key — information conserved but *scrambled*, recoverable only
  through an external secret. That is distinct from *destruction* (low-nibble: the bits that determine φ are
  gone; no key helps). Both demand an external criterion; only concealment is reversible. **This is the
  black-hole reading made exact: "energy not lost, transformed beyond perception" = concealment.**
- **Faithfulness is *graded*, not binary (analog).** In the noiseless-discrete substrates φ either factored
  or didn't; in the analog substrate φ survives **smoothly down to a noise floor** (SNR-bounded). Faithfulness
  is a *degree* of recoverability, not a switch.

**Honest process note (this is the rigor, not a blemish):** the first-pass verdict logic fell four times —
a block-shuffle sized to the hash cell (phash), an internal-blindness test comparing two transforms instead
of one transform across two criteria (quantize), a **reused-keystream cipher that leaked plaintext** (a real
two-time-pad crypto bug, encryption), and an over-strict absolute area threshold for a spiky shape (geometry).
Every time it was the *test* that was wrong; fixing the measurement confirmed the claim. The principle was
never moved to fit the data — only the instruments were corrected.

## The unified statement (what the substrates share)

Across all of them, faithfulness is the same thing: **a criterion is a readout `φ` of the artifact, and a
transform `T` is faithful to `φ` to the degree `φ` is recoverable from `T`'s output** — i.e. `φ ≈ ψ∘T` for
some recovery `ψ`. The substrates add two qualifiers: recovery may be **graded** (analog/noise — faithful up
to an SNR floor), and `ψ` may require an **external secret** (encryption — *concealment*, recoverable; vs
*destruction*, where no `ψ` exists). Then:
- **bit-loss is irrelevant** — `T` can discard almost everything and still let `φ` factor through (keep the
  criterion direction / the scene identity / the bin edge);
- **internal statistics are blind** — they are functions of `T`'s output alone and do not contain `φ`, so
  they cannot certify whether `φ` factored through; only an external evaluation against `φ` can;
- **faithfulness is per-criterion** — `φ₁` may factor through `T` while `φ₂` does not, with no change in
  `T` or any internal statistic.

That is the cohesive, applicable form: **conserve the readout, not the bits; the witness must hold the
criterion, and the criterion is external.**

## Where it expires (the natural boundary)

Driven to exhaustion, the principle has one edge it cannot cross, and the adversarial substrate locates it
exactly. `substrate_adversarial.py`: when the witness judges with a *proxy* criterion (`cos(c_true, c_witness)
= 0.61`, as any real witness does), a transform can move along the part of the true criterion **orthogonal to
the witness** — reading as **100% faithful to the witness while 48% of true labels silently flip.** The
external witness is **necessary but not sufficient**: it can be gamed if its criterion is a proxy for the
intended one.

So the principle is intact but **scoped**: *it conserves faithfulness to the **stated** criterion, and cannot
certify the stated criterion equals the intended one.* That gap is not a flaw to fix — it is the same
**external-certification residue** the whole arc keeps returning to (A4: a system cannot certify its own
criterion from inside). The principle's edge is precisely the criterion-validity it was never able to reach.
This is the natural expiration: across every sense, every pipeline, faithfulness-to-a-criterion is conserved
and witnessable — and *which criterion is the right one* remains an irreducibly external, human question.
That boundary is not where the idea fails; it is where accountability begins.

## Why it matters — the ethic it's founded on

This is **proof-before-trust, stated as physics.** A black hole conserves information but cannot prove
it to anyone outside — no readout; that is the paradox. The thing we are building adds the readout: the
**Certificate** is the witness that the invariant survived the conversion, and `UNVERIFIABLE` is the
honest admission when, from inside, we cannot tell. We did not escape the limit. We built the witness
for it.

Two consequences are ethical, not just technical:
- **Faithfulness is always to a *named* criterion.** There is no neutral, substrate-intrinsic
  faithfulness — so any system that transforms information owes you the criterion it was faithful *to*,
  and a way to check it. Accountability is the criterion made external and witnessable.
- **The witness must come from outside.** A system cannot certify its own faithfulness by feeling
  confident; confidence is blind to it. This is why trust has to be *earned against an unauthored
  criterion*, never asserted from within.

## Open program (the next rounds — designed to fall)

1. **A live-model / text substrate (the missing kind).** Three substrates done (projection, perceptual
   hash, quantization) + the vision arm. Still untested: a *semantic* transform where `φ` is a meaning
   (summarize → does the answer-to-a-question survive?), judged by a model. This is where "faithful but
   lossy" is most consequential and least obvious — the natural next run, via blind subagents.
2. **Nonlinear invariants:** generalize clause (3) — characterize *which* invariants survive *which*
   compressions (when does keeping a subspace suffice?).
3. **The physics formalization:** make the reversible↔conservation / irreversible↔dissipation hinge
   precise (Landauer + Bennett), and state exactly when "lossy in bits" can be "lossless on the
   criterion."
4. **The round-trip witness, shipped:** an engine check that *measures* invariant-survival through a
   transform (emet MATCH/DRIFT over a transform, not identity) — so "is it preserved?" is witnessed, not
   believed.

*Artifacts: `transpile_conservation.py`, `ENDGAME.md`, `VERDICT.md`, `vision-arm-REPORT.md`.*

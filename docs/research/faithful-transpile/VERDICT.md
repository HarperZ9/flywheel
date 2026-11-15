# The Aperture — Proof-or-Disproof Verdict

> Adversarial re-audit of `HANDOFF.md` and the `aperture-commons-thesis` anchor.
> Date: 2026-06-23 · Method: reproduce every sim, audit whether each verdict *follows from
> the code*, then build the two runnable probes the handoff flagged as open and try to break
> the survivors. New artifacts: `probe_ownerless.py`, `probe_gate.py`.

---

## 0. What "proof or disproof" can mean here (read first)

The package contains three different kinds of claim, and they are not provable to the same degree:

1. **Arithmetic claims** — "in *this* seeded dynamical system, X happens." Fully checkable: run it,
   read it, attack it. This is where a real verdict is possible.
2. **The depth law `f* ≈ 1/(1+ρ)+0.07`** — an empirical *fit* in one model family. Checkable as a fit;
   not derived.
3. **The thesis proper** — aperture = singularity = pupil = synapse; "the answer is the ownerless
   fixed point against an unauthored criterion." These are **interpretive identifications**. The sims
   can *illustrate and stress mechanisms* that the thesis points at; they **cannot prove the thesis
   about reality.** A hand-built dynamical system that behaves as predicted is a consistency
   demonstration, not evidence that human↔model reconciliation, cosmology, or neurobiology work this way.

So the honest headline: **a full proof of the package is not available, and the package is not
disproven either.** What follows is the strongest verdict that *is* available — reproducibility,
validity-of-each-verdict, and two new attacks that change two of the ledger's lines.

---

## I. Reproducibility — CONFIRMED (high confidence)

All five sims run on Python 3.12.10, stdlib only, and reproduce the ledger's numbers **exactly**:
commons err 0.0000 vs best solo 2.8013; naive tipping 2/9, gated 4/9; fair-law residual +0.072
(std 0.018) → `1/(1+ρ)+0.07`; gate gain flat +0.23/+0.29/+0.29/+0.27 across D=2/8/32/64; the
σ-boundary that the teardown refuted. No drift, no cherry-picking found in the seeds shown.

---

## II. Per-claim audit (does the verdict follow from the code?)

| Ledger claim | Audit verdict |
|---|---|
| Blind agents reconcile to a truth none can see (err 0.000 vs 2.80) | **HOLDS, but the exactness is by construction.** Linear/convex world + guaranteed coverage (every dim seen by ≥1 agent) ⇒ unique fixed point at `t`. The *qualitative* win is real and non-trivial (the consensus channel transports unseen-dim info); the *0.0000* is baked in. Hidden load-bearing assumption: **union-of-sight = complete.** Disclosed honestly in the anchor. |
| VOID → truth-blind centroid | **HOLDS, trivially** (criterion off ⇒ converge to centroid of starts). |
| BATTLE → collapse to authored | **HOLDS, trivially** (pull to a fixed agent that never moves). Note "battleground" here is modeled as *one dominant center*, not a contested fight — a modest claim, not the dramatic one the word implies. |
| Toggle criterion → regime flips (P4) | **HOLDS, but it is a smooth monotone knob, not a bistable flip.** Calling the two ends "two regimes, same place" is interpretive gloss on a continuous curve. |
| Sincere disagreement obeys the depth law (`f*≈1/(1+ρ)+0.07`) | **HOLDS as a fit** (one family, neutral starts, +0.07 post-hoc). Form confirmed; constant measured, not derived. |
| Loudness > depth makes a lie dangerous | **HOLDS** and is the most interesting real result. The "unphysical undamped adversary" is better read not as *wrong* but as **a second, legitimate threat model — the loud liar** — governed by force, not depth. The handoff's synthesized conclusion lands here correctly even though the table calls it "unphysical." |
| Coordination is the weapon | **HOLDS** (random f*=0.72 vs coordinated 0.18). |
| **Ownerlessness / rescue-from-anywhere** | **PARTIALLY DISPROVEN — see §III.A.** Worse than the anchor's "good-faith-only" qualifier. |
| **The gate caps loudness at the seam** | **HOLDS AND HARDENS, with a newly-surfaced precondition — see §III.B.** |
| Gate survives high dimension (natural attack) | **HOLDS** (reproduced). |

---

## III. New evidence — the two probes the handoff flagged as open

### A. Ownerlessness is a start-distribution artifact (partial DISPROOF) — moderate-high confidence

`contested_aperture.py` Q-A reports **30/30 reach the true well even when seeded near the decoy**,
read as "criterion *depth*, not start, decides." But its starts are `uniform(-5,5)^8`, whose centroid
sits on the origin ≈ `t`, while the decoy `q` sits ≈8.5 away. The consensus pull `K` drags everyone to
that centroid — i.e. **toward `t` because the cloud was centered on `t`.**

`probe_ownerless.py` holds the world and dynamics identical, **zero adversaries**, and only slides the
start-cloud center along the `t→q` axis (`α=0`→t, `α=1`→q):

```
 jitter  α     reached TRUE/30   reached DECOY/30
   5.0  0.00       30/30              0/30
   5.0  0.50       21/30              9/30
   5.0  1.00        0/30             30/30
   1.0  0.50       30/30              0/30      (tight cloud)
   1.0  0.75        0/30             30/30
```

**Truth wins only when the start cloud is centered on truth.** Center it on the decoy and the decoy
wins 30/30 — in *pure good faith*, with the true well still the deeper one. The deep well does **not**
"rescue from the decoy basin." The anchor already qualified this to "good-faith-only … collapses under
*attack*," but the collapse is present with **no adversaries at all** — it is plain basin-of-attraction
path-dependence. The "ownerless under non-convexity" line should be retired, not just qualified.

### B. The gate survives the worst-case attack — *if the readout is also gated* (HARDENS + a caveat) — moderate-high confidence

Open question #2: the median gate was only tested against the *natural* attack (all adversaries pull
toward the one point `q`). `probe_gate.py` builds the attack coordinate-wise median is theoretically
weakest against — **coordinate-decomposed** (shove each axis independently toward the decoy side) and
**extreme** (teleport to a far extreme each step) — across D=2/8/32/64.

First finding (a flaw in the *original* sims): **every original sim reads the final answer out as
`_mean(agents)` even in gated mode** (verified: `contested_aperture.py:87`, `teardown.py:114`,
`run_gaps.py:80`, `map_boundary.py:74`). The gate governs only what agents pull *toward*, not how the
answer is read. Against an *unbounded* adversary the mean readout breaks at **one** adversary
(f*=0.08=1/12) regardless of the gate — the mean has breakdown 1/N. The gate looked robust before only
because the natural adversary is *bounded* (it pulls toward the finite point `q` and is itself damped by
consensus).

Second finding (the answer to Q#2): read the answer out with the **same robust aggregator the gate
uses**, and the gate holds against the purpose-built attacks:

```
 adversary = decomposed        adversary = extreme
  D    mean   median           D    mean   median
  2    0.08   0.48             2    0.08   0.48
  8    0.08   0.48             8    0.08   0.48
 32    0.08   0.44            32    0.08   0.44
 64    0.08   0.38            64    0.08   0.35
```

The median holds near its ~0.5 per-coordinate breakdown, with only mild high-D softening (→0.35–0.38 at
D=64), while the mean collapses to single-adversary breakdown. **So the gate is *more* robust than the
open question feared — but its defense requires gating the *readout*, not only the consensus target, a
precondition the original sims state implicitly and their code actually violates.** The sharpened thesis
line: *the membrane must cap loudness at the readout, not just at the pull; a gate that governs the
conversation but reads the result out as a raw average defends against bounded liars and fails to a
single unbounded one.*

---

## IV. The vision arm — NOT run; tooling is present, the blocker is methodological (high confidence)

A native rasterizer **is** available (`PIL 12.2.0`), and all referenced inputs exist
(`context-experiment/v2-synthesis-questions.md`, `tools/context_pack.py`,
`maps/CONTEXT-PACK.json`). So Section V's "if no renderer, stop" exit does **not** apply — rendering is
feasible.

The real blocker: a valid test needs a **blind** multimodal judge. I already hold the full thesis,
sims, and structure in context, so any image I "perceive" myself is contaminated — that would be the
fabrication Section V forbids. The clean version is constructible: render the relational graph to PNG
with PIL, then dispatch **fresh-context subagents** — one given only the image, one only the equivalent
text graph — pose the identical synthesis questions, and score both blind against the key. That is a
legitimate (if single-model, small-N) vision arm. I did **not** run it here because doing it to a
standard where it can actually *fail* is a distinct experiment, and a rushed self-judged version would
be worse than no result. **Recommendation: run it next as a blind-subagent harness; do not fold a
half-built version into this verdict.**

---

## V. Bottom line

- **Reproducible:** yes, exactly. (high)
- **Verdicts follow from the code:** mostly yes, with several "true but by construction / trivially /
  smooth-not-bistable" caveats that the prose oversells in places. (high)
- **Two ledger lines change under new attack:** ownerlessness is a **start artifact** (partial
  disproof, beyond the anchor's qualifier); the gate **hardens** against the worst-case attack but only
  with a **gated readout** the original code lacks. (moderate-high)
- **Thesis proper:** **not proven and not disproven** — it is an interpretive frame the arithmetic can
  illustrate and stress, not adjudicate. The sims are honest mechanism demonstrations inside a chosen
  model; the leap to cosmology/neurobiology/human-model reconciliation is analogy.
- **Vision arm:** untested; runnable next via a blind-subagent harness; not blocked by tooling.

The package's real intellectual integrity is that it *was built to break and one piece already did*
(the σ-boundary). This audit continues that: two more pieces moved under attack. That is the thesis
behaving as designed, not failing.

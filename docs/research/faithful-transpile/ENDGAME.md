# The Aperture — Endgame (probes & steelmans run to exhaustion)

> Directive: run the probes and steelmans until nothing is left; where something is proven wrong and
> an adjacent solution is proven, carry it to its end. Date 2026-06-23. This is the terminal pass over
> the simulable claims. Detail in `VERDICT.md` (round 1) + the `probe_*.py` artifacts.

## Scoreboard

| Front | Status | Outcome |
|---|---|---|
| A1 readout flaw | **carried to end** | gate must cap the *readout*, not just the consensus target |
| A2 ownerlessness | **carried to end** | replaced false "ownerless" with a measured basin separatrix |
| A3 depth law | **corrected, carried to end** | law form robust; the "+0.07 coverage bonus" was a finite-N artifact |
| A4 criterion certification | **proof-of-limit** | no internal statistic certifies truth — irreducible, by design |
| B1 vision arm | **carried to end** | v1's loss was *layout salience*, not channel; neutral render closes the gap |
| Thesis proper | **not adjudicable** | aperture=singularity=synapse is interpretive; arithmetic can't settle it |

---

## A1 — readout (proven wrong → fixed). `probe_readout.py`

Corrected canonical tolerances f* (fraction of adversaries truth survives):

| adversary | target | readout | f* | |
|---|---|---|---|---|
| bounded | mean | mean | 0.22 | the naive commons |
| bounded | median | mean | 0.46 | **the old "44%" headline — bounded-adversary-only** |
| bounded | median | median | 0.50 | corrected gate |
| unbounded | mean | mean | 0.11 | |
| unbounded | median | mean | **0.11** | **gate target + mean readout COLLAPSES (≈1/N)** |
| unbounded | median | median | **0.48** | corrected gate restores tolerance |

**End state:** the gate's defense is real only when the *readout* is also gated. The original sims read
`_mean(agents)` even in gated mode, so against a committed (unbounded) liar they break at one adversary.
Canonical claim = gate target **and** readout → ~0.48–0.50 against both bounded and unbounded adversaries.

## A2 — ownerlessness (proven wrong → replaced). `probe_basin.py`

The false "ownerless / reaches truth from anywhere" claim is replaced by a measured basin separatrix
α\*(ρ) — the start fraction (t→q) at which truth stops winning, all good faith, no adversaries:

```
 ρ     0.40  0.55  0.70  0.85  1.00  1.20
 α*    0.59  0.56  0.54  0.52  0.51  0.49
```

**End state:** a near-midpoint boundary (α\*≈0.51 at ρ=1, exact depth symmetry) with only a mild depth
tilt (~±0.1 across the whole ρ range). So **start position dominates; depth only tilts the boundary** —
the precise inversion of the original "depth, not start, decides." Path-dependence is governed, not absent.

## A3 — depth law (interpretation proven wrong → corrected). `probe_law.py`

- **Form is robust:** f* ∝ 1/(1+ρ) survives weak/strong consensus (K=0.15–0.45) and commons size N=6–20
  (residual stays small, doesn't swing with ρ).
- **The "+0.07 coverage bonus" is refuted.** The residual c does **not** track mask coverage (≈0.07–0.11
  flat across sight p=0.5→1.0, and *positive even at full sight* p=1.0 — the opposite of a coverage story).
  It tracks **1/N**: c = 0.114, 0.069, 0.050, 0.031 for N = 6, 12, 24, 48 — i.e. the f* estimator's
  quantization step. **End state:** the law is `f* ≈ 1/(1+ρ)`; the +0.07 was a finite-N (N=12) artifact,
  not a physical bonus, and the anchor's coverage interpretation is wrong.

## A4 — criterion certification (open → proof-of-limit). `probe_criterion.py`

A *more seductive* decoy (deeper w=1.4 + wider σ=3.2 than the true well w=1.0, σ=2.2) captures the commons
when started near it — and the wrong attractor is **internally indistinguishable** from the right one:
spread 0.0000 both, convergence **6.7 steps (decoy) vs 6.8 (truth)** — the wrong well is marginally
*more* confident — residual 0.0 both. **End state:** no internal statistic (spread, speed, gradient
residual) separates truth from the best attractor. The criterion that names which well is truth must come
from **outside the tube**. This is the irreducible residue, now a proof-of-limit *within* the model — it
cannot be "carried further" by arithmetic, which is exactly the thesis's claim.

## B1 — vision arm (loss proven to be layout, not channel → fixed). `render_graph_v2.py`, `vision-answers-v2/`

Round 1 (`vision-arm-REPORT.md`): same relational graph as text vs as a diagram image; **shared seeing
lost by +4.0** (both blind judges), via spatial salience — the diagram centered `accountable-surface`
(wrong node) + a loud flagship tag + a bidirectional-looking arrow, and both visual subjects picked it for
S2 and shared a fabricated "edge to emet."

Round 2 — neutral re-render fixing exactly those three confounds (center the true convergence node
`coherence-membrane`, unambiguous per-direction arrows, subtle flags), same blind harness:

| | text avg | visual avg |
|---|---|---|
| Judge 1 (default) | 13.5 | 12.5 |
| Judge 2 (Haiku) | 13.0 | 14.0 |
| **mean** | **13.25** | **13.25** |

**Dead even. Both visual subjects got S2 right; zero visual hallucinations** (the only flag was in a text
set). **End state:** the channel (image vs text) is ~neutral for synthesis; what decides is whether the
representation's *salience structure matches the real topology*. v1 (salient ≠ true hub) → −4; v2 (salient
= true hub) → 0 brackets the causal variable: **salience, not channel, is the lever.** This sharpens the
spatial-context thesis — "the shape" helps only when the rendered shape is *faithful*; a misleading layout
actively hurts. The optimistic "render it and the model sees more" is still unsupported; the corrected
claim is "render it *faithfully* and it matches text; render it misleadingly and it loses."

---

## What is left: nothing arithmetic can settle

Two irreducibles remain, both *by design* beyond these sims:
1. **The criterion-certification residue (A4)** — provably unclosable from inside the model. Closing it
   needs an *external* certifier (the witness layer / Certificate / Telos) — an architecture question, not
   a simulation. That is the project's actual forward work, not a probe.
2. **The thesis proper** — aperture = singularity = synapse is an interpretive identification. The sims
   stress its mechanisms (and broke three sub-claims); they cannot prove or disprove the identification.

Every simulable claim has now been attacked and either held, was corrected with its replacement proven, or
hit a proof-of-limit. The probes are exhausted.

*Artifacts: `probe_readout.py` `probe_basin.py` `probe_law.py` `probe_criterion.py` `probe_gate.py`
`probe_ownerless.py` `render_graph.py` `render_graph_v2.py` `ecosystem-graph{,-v2}.png`
`vision-answers{,-v2}/` `vision-arm-REPORT.md` `VERDICT.md`.*

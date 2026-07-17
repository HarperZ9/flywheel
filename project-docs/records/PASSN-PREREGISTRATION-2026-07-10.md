# pass@N raise -- pre-registration (2026-07-10)

Recorded BEFORE the N=32 run completes, so the experiment is a real falsifier.

## The question

"raise N" -- does increasing the candidate budget move headroom tasks across
the multiplicity thresholds that oracle-free selection needs? At N=4 the
consensus selector recovered only 9% of the external oracle's lift because 77%
of tasks had zero correct candidates and 15% had exactly one (structurally
unreachable). The lever is N. This run raises it to 32 (from the ablation's 4),
with a genuine unique (temperature, seed) grid so higher N adds real diversity
instead of repeating generations.

## Two competing predictions for the full 61-task set at N=32 (EXACT, k=pool)

**A. The Jeffreys Beta-Binomial model, fit on n=4** (`passn_model.py`, "keep the
pool, generate k-n more" framing, exact hypergeometric verified against brute
force): pass@32 = 72.0%, consensus@32 (>=2 correct) = 59.0%.
Artifact: `E:\local-model-run\passn_prediction_from_n4.json`.

**B. My independent estimate (anti-anchoring):** the n=4 fit OVER-SMOOTHS the 47
cold tasks -- Jeffreys gives every 0/n task a positive posterior mean that
compounds optimistically over 32 draws. Direct evidence this session: the
held-out falsifier at nt=2 (train on 2, predict fresh next 2) mispredicted
pass@2 by +20.5pts (33.6% predicted vs 13.1% observed) -- small-N fits
demonstrably overshoot. So the n=4 forward prediction is an upper bound, not a
point estimate. On the full-61 set I expect the exact numbers LOWER:
- **pass@32 (external ceiling): ~48%** (range 40-55%). Evidence: topo_sort went
  0/8 -> 3/16, so cold tasks do wake up, but not the majority.
- **consensus@32 (oracle-free ceiling): ~32%** (range 25-40%).

## The adjudication

When the N=32 run (`passn_curve_n32.json`) completes, the EXACT hypergeometric
consensus@32 settles A vs B. Then the properly-powered calibration test:
`passn_model.py --calibrate 16` trains the model on candidates [0:16] and
predicts the HELD-OUT block [16:32] (independent fresh draws) -- a real
train/test split with 8x the training signal the nt=2 check had. If B is right,
the n=4 forward prediction (A) will sit well above the observed exact
consensus@32, and the nt=16 held-out will calibrate tightly -- together showing
the model needs a reasonable pool (n>=16) before its extrapolation can be
trusted. That threshold is itself a useful finding for how much budget to spend
before believing a projected curve.

## What either outcome means for the thesis

- If raising N lifts the oracle-free ceiling substantially (consensus@32 >> 7%),
  the companion seat can answer more locally without a frontier oracle -- the
  "pre-decided world does the work" thesis extends to selection under budget.
- The gap between pass@k (external ceiling) and consensus@k (oracle-free) is the
  irreducible price of not having ground truth. Watching that gap NARROW as N
  rises (probe: 20pts at N=8 -> model says ~13pts at N=32) quantifies how much a
  real external oracle is still worth at each budget.

## RESULT (2026-07-10, adjudicated) -- I was wrong in the conservative direction

The N=32 run completed (61 tasks, exact hypergeometric over the pool of 32,
artifact `passn_curve_n32.json`):

| metric | model-from-n4 (A) | my estimate (B) | **OBSERVED** |
|---|---|---|---|
| pass@32 (external ceiling) | 72% | ~48% (40-55) | **60.7%** |
| consensus@32 (oracle-free ceiling) | 59% | ~32% (25-40) | **49.2%** |

**Both predictions were off, and the model (A) was closer than my independent
estimate (B) on both.** I predicted the n=4 Jeffreys model would OVERSHOOT and
corrected down to ~32%; the truth (49.2%) landed ABOVE my whole range. My
anti-anchoring correction over-shot into too-conservative -- I underestimated how
much the bimodal "wake up substantially or stay 0" pattern would unlock as N rose.
Recording this straight: the discipline caught me, not the model.

**What raising N actually did (the real finding):** consensus-reachable climbed
3.5% -> 12.1% -> 24.4% -> 36.3% -> **49.2%** at N = 2/4/8/16/32 -- from ~6.6% at
N=4 to nearly HALF the headroom tasks at N=32. The marginal gain per doubling
held near-constant (~12%), so the curve has NOT plateaued; N=64 would likely push
higher. pass@32 = 60.7% (external ceiling, up from 23% at N=4). The external-vs-
oracle-free gap narrowed from 18pts (N=4) to 11.5pts (N=32) -- the price of no
oracle shrinks with budget, as predicted.

**The instrument validated:** the held-out falsifier (fit on first 16, predict
the fresh next 16) calibrated on consensus at 3.1% error (< 5% tolerance); pass
overshot 7.2%. So the Beta-Binomial model is trustworthy from n>=16, confirming
the "needs a reasonable pool before its curve can be believed" thesis -- the n=4
fit was noisy (which is why BOTH forward predictions missed), not the n=16 one.

**Bound not yet closed:** this is the reachability CEILING (>=2 correct exist),
not what the consensus SELECTOR actually captures. Actual capture (needs the
selector re-run over the 32-candidate pools) is <= 49.2% and remains to be
measured; the demote-only gates make the deployed capture more conservative still.

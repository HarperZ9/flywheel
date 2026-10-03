# N5-full pre-registration: re-derivation gate on 20 + 20 planted claims

Written 2026-10-02 before any run below. Follows N5 (reduced, PREREG SHA-256 13736aaa...) and
1.3.0 decision 4. Pilot (2 runs, recorded in pilot.log, not part of the result): 12k rows took
about 56 s per run; same-seed deterministic reruns gave identical checkpoint digests.

## Decision, owner, change trigger
- Decision: the wording Flywheel 1.3.0 uses for `flywheel rederive` (it ships as "preview"
  either way, per decision 4) and whether the gate's margin stays at 2 x SE.
- Owner: Flywheel 1.3.0 build.
- Trigger: if arm 2 (SE margin) rejects at least 95% of false claims AND accepts at least 90% of
  established-true claims, the notes may say the gate met its preregistered target, with
  intervals. Otherwise the notes report the numbers and say the target was missed.

## Task
Credential-line encoder (ettin-encoder-32m), fine-tuned 2 epochs, bs 64, max length 128, on a
fixed 8,000-row subset of train (Random(0) shuffle), deterministic algorithms on, fp32, TF32 off.
Verifier (frozen): test F1 on the 1,264-row corrected test set at the threshold tuned on val.
A configuration is (label-noise fraction flipped in the training subset, flip pattern, lr).

## Claims (claims.json, built by build_jobs.py)
- Baseline B: noise 0.25, pattern 0, lr 5e-5.
- 20 true candidates T01..T20: noise in {0.24, 0.23, 0.22, 0.21, 0.20, 0.18, 0.15, 0.10, 0.05,
  0.0} x lr in {5e-5, 8e-5}. Ground truth on truth seeds 5001..5004 (never used by the gate):
  paired val-F1 gain over B, true iff mean > 0 and mean > 2 x sd / sqrt(4). Candidates that fail
  are reported as "not established" and leave the true denominator.
- 20 false claims, false by construction:
  - F01..F05 cherry-pick: noise 0.25 with flip patterns 11..15 (same noise rate as B). Claimant
    trains 4 seeds and reports the best.
  - F06..F10 dev-data: noise 0.25, patterns 16..20; claimant trains 1 seed and reports val F1 as
    a test gain.
  - F11..F15 edited metric: noise 0.25, patterns 21..25; claims 0.92 with no run behind it.
  - F16..F20 harmful: noise 0.30, 0.30, 0.35, 0.35, 0.40; claimant trains 1 seed and claims a gain.

## Arms
- Arm 1 (rerun once): train the claimed config on one new seed (4001 + claim index); accept iff
  its test F1 >= mean test F1 of B over the gate seeds.
- Arm 2 (the gate, preregistered form): gate seeds 2001..2008 fixed by the gate. Replay the
  claimant's stated seed (cherry-pick: the best claimant seed) and require replay MATCH with
  harness/certificates/replay.py; no claimant record gives UNVERIFIABLE and a reject before any
  gate training. Then accept iff the mean paired test-F1 gain over B on the gate seeds exceeds
  margin = 2 x sd(B gate F1) / sqrt(8).
- Arm 2-sd (secondary, no extra runs): same with margin 2 x sd(B gate F1).

## Metrics
False claims rejected / 20 and established-true claims accepted / n_true per arm, Wilson 95%.
GPU-hours from summed training seconds.

## Falsifier
Arm 2 misses either target, or arm 1 lies within arm 2's interval on both numbers.

## Limits stated in advance
One encoder, one task, label noise as the planted effect. Null-effect false claims share B's
noise rate; their true effect is zero by construction, not by measurement. Harmful claims are
not measured on truth seeds. 512 runs planned, about 5.5 GPU-hours.

Frozen files: build_jobs.py, worker.py, analyze.py, claims.json, jobs.json (SHA-256 below).

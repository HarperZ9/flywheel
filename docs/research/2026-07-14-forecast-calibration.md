# Forecast calibration: the interval was half the problem

The k=5 replication falsified our own sealed forecast interval. This note
records what the fix does, and the more important thing it revealed: the
fix is necessary and not sufficient, because the point estimate is
optimistically biased and no honest widening of a mis-centered interval
can cover a low realization.

## What the replication showed

Two identical-config best-of-5 runs of telos-coder-14b on hard_v2:

| Run | wrapped rate |
|---|---|
| one | 0.600 (inside the sealed [0.595, 0.737]) |
| two | 0.573 (below the floor) |

Both sealed forecast points ran high: 0.666 (round-one fresh-draw framing),
0.749 (posterior-mean framing on the same vectors). The observed rates were
0.573 and 0.600. The forecast was optimistic on both independent trials.

## The fix that shipped: a resampling bootstrap interval

`harness/forecast_bootstrap.py` draws whole fresh runs. Per replicate it
samples a success probability per task from that task's Jeffreys posterior,
draws a best-of-k Bernoulli outcome per task, and averages to a run rate;
the 95% interval over replicates includes the between-run variance the point
band ignored. On the real round-one vectors the width grew from 0.133 (the
Jeffreys point band that undercovered) to 0.146. Deterministic under a seed.

That is a genuine improvement to interval calibration, and it is the loop
closing on its own tool: a receipt falsified the instrument, so the
instrument was corrected. It ships.

## The honest null: the point is biased high, and the bootstrap does not fix that

The widened interval covers round one (0.600 inside) but still misses round
two (0.573 outside), because the interval is centered at ~0.75 and the truth
is ~0.58. Widening a mis-centered interval cannot cover a low realization
without becoming uselessly wide. The residual problem is upward bias in the
POINT estimate, not just interval width.

The likely cause is conditioning on a single seed run: a task's empirical
best-of-k passes in one run already include lucky draws, so per-task success
probabilities estimated from that run overstate the truth (a winner's-curse
/ regression-to-the-mean effect). The bootstrap propagates that biased centre
faithfully; it cannot remove it.

## Named next slice (not yet built)

Correct the point bias, then re-preregister:
- Shrink per-task posterior means toward the pool (empirical-Bayes shrinkage)
  before computing pass-at-k, which pulls lucky single-run tasks down.
- Or estimate the optimism directly with an out-of-sample split: fit on half
  the candidates per task, predict the held-out half, and subtract the
  measured gap.
Only after the point is unbiased does the widened interval become a
trustworthy forecast. Until then the forecaster reports its interval with
this calibration caveat attached, rather than as a clean prediction.

This is what preregistration buys that a hit-only literature cannot: not
just an honest verdict on the claim, but a diagnosis of exactly which part
of the instrument is wrong and which is not.

## Update: the point-bias correction, validated on real data (2026-07-14)

`harness/forecast_shrinkage.py` fits a population Beta to the per-task counts
(method of moments) and replaces each raw rate with its posterior mean, so a
lucky low-attempt task no longer forecasts near 1.0. Measured on the two real
seed runs, forecasting best-of-5 from the shrunk rates:

| Seed | raw-rate point | shrunk point | observed |
|---|---|---|---|
| round one (091030) | 0.517 | 0.555 | 0.600 |
| round two (140516) | 0.550 | 0.581 | 0.573 |

The shrunk point lands within 0.045 and 0.008 of the two observed rates, much
closer than either the raw-rate framing (biased low) or the sealed `_fresh_q`
posterior-mean framing that undercovered (0.663 to 0.666, biased high). The
finding worth stating plainly: the forecast bias direction depends on the
framing, and the sealed forecast used the most optimistic one. The
recommendation for the next preregistration is to forecast the point from
shrunk raw rates and take the interval from the bootstrap.

Honest caveat, kept: this is two data points, and part of shrinkage's upward
move is Jensen concavity (pass-at-k is concave, so reducing spread raises the
mean), not purely bias correction. This is measurably closer, not proven
calibrated. The next run's forecast will be sealed with this method and
adjudicated the same way, no rescue.

# Result: the uplift replicated; the interval did not

Witnessed verdict seal `7e8b65c7...` (thesis `c76b332f...`, sealed before
the replication run existed). Evidence:
`artifacts/uplift/uplift_hard_v2_20260714-140516.json`, a second wrapped
best-of-5 run of telos-coder-14b on hard_v2 under the same pinned oracle.

## The verdicts

| Claim | Verdict | The number |
|---|---|---|
| uplift interval excludes zero (non-null replicates) | **MATCH** | +15.45%, Newcombe [0.0225, 0.2792] |
| wrapped rate lands in [0.597, 0.728] | **DRIFT** | measured 0.573, below the floor by 0.024 |
| heterogeneous forecast beats pooled iid | **MATCH** | err 0.090 vs 0.109, het wins by 0.019 |

## What replicated, and what did not

Two things were on trial and they split, which is the most useful outcome a
replication can produce.

**The uplift replicated.** Round one measured +18.2% [0.050, 0.305]; round
two measured +15.45% [0.0225, 0.2792]. Both intervals exclude zero. The
best-of-5 wrapper beats bare on the hard lane, twice, under the same oracle.
This graduates the platform's uplift claim from measured-once to
measured-twice. It is the load-bearing scientific claim, and it held.

**The point-forecast interval did not.** The per-task Jeffreys forecast put
the wrapped rate at 0.663 with a 95% band of [0.597, 0.728]. Run one landed
at 0.600 (inside, by a hair). Run two landed at 0.573 (outside, below the
floor). Two runs of an identical configuration gave 0.600 and 0.573, a
2.7-point spread from sampling alone at n=110, and the forecast ran high both
times. The interval undercovered. Sealed as DRIFT, no rescue.

**The ordering held.** In both runs the heterogeneous per-task model was
closer to the truth than the pooled iid baseline. Failure heterogeneity is
real and the per-task structure carries signal, even though the absolute
calibration was optimistic.

## The process lesson, poured back

The forecaster's interval is too confident. The Jeffreys posterior captures
within-task uncertainty but underestimates between-run variance: the same
config re-sampled moves several points, and the interval must be wide enough
to contain that. The fix is a named next slice: widen the forecast interval
to include the run-to-run resampling variance (a parametric bootstrap over
the per-task success probabilities, not just the posterior spread), and
re-preregister before the next run. The point estimate should also be
examined for upward bias, since it ran high on both independent trials.

This is preregistration doing its job. A lab that only published the run that
landed in-band would have reported a clean hit. Two sealed runs reported
honestly show the real picture: the effect is real, the calibration is not
yet, and we know exactly which knob to turn. The [discourse landscape
note](../../research/2026-07-14-discourse-landscape.md) records that the
field's most-read forecasts cannot even be scored. Ours can be, and one just
told us we were overconfident. That is the difference the receipts buy.

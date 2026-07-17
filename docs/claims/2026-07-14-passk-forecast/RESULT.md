# Result: the sealed forecast held; the rival is falsified

Witnessed assessment seal `63722ae5...` (thesis `0db6e0f4...`, sealed
before the bench existed). Re-emitted 2026-07-15 as a full re-derivable
record: the original summary displayed seal `cd6d75b1...` without its
preimage on disk, so no stranger could recompute it. Same thesis, same
measurements, same frozen rule, verdicts unchanged. Evidence:
`artifacts/uplift/uplift_hard_v2_20260714-125209.json`, the wrapped
best-of-5 run of telos-coder-14b on hard_v2, same pinned oracle.

## The verdicts, per the frozen rule

| Claim | Verdict | The number |
|---|---|---|
| interval [0.595, 0.737] | **MATCH** | measured 66/110 = 0.600, deviation 0.066 within 0.071 |
| heterogeneous beats iid | **MATCH** | err 0.066 vs 0.159; wins by 0.093 |
| iid beats heterogeneous | **DRIFT** | the registered rival is falsified |

The measured rate landed 0.005 above the sealed floor: a close call
the interval survived, recorded as exactly that. The per-task Jeffreys
model, built from nothing but the best-of-3 run's censored outcome
vectors, predicted a fresh best-of-5 within 6.6 points; the pooled
iid baseline missed by 15.9. Failure heterogeneity is real: tasks are
not exchangeable coins, and a forecast that respects per-task
structure beats one that pools it, on the first and only trial both
were sealed for.

## What was NOT sealed, reported as what it is

The same artifact measures bare 46/110 (41.8%) vs wrapped best-of-5
66/110 (60.0%): **uplift +18.2%, Newcombe 95% [0.050, 0.305], the
interval excludes zero.** This is the first non-null uplift measured
for the platform's own model on the hard lane (best-of-3 read +10.9%
including zero this morning). It was not a sealed claim, so it enters
the record as a measured result awaiting replication, not as a
vindicated prediction. One replication run under the same pinned
oracle would move it from measured-once to measured-twice; the
distinction stays visible until then.

## What this cycle demonstrates

Measured per-model diversity, a content-addressed forecast sealed
before the bench, a registered rival denied the chance to pick its
moment, and a mechanical adjudication the day the evidence landed.
The same day's research note (2026-07-14-discourse-landscape.md)
records that the field's most-read forecasts cannot be scored at all
because their readouts were never sealed. Both facts are now in one
repository, and each is the other's argument.

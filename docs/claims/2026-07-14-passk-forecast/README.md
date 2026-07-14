# Sealed forecast: telos-coder-14b, fresh best-of-5 on hard_v2

Sealed 2026-07-14, before any best-of-5 run of this model exists.
Source evidence: the completed best-of-3 lane
(`artifacts/uplift/uplift_hard_v2_20260714-091030.json`), whose
censored per-task records reconstruct exact candidate sequences.

Two models are pre-registered side by side in one sealed artifact
(`FORECAST-14B-K5.json`, seal
`5fdaadfce7ccd521e567d0bfdee26940d051eea6807359527f8b2291fd8f2bc8`):

| Model | Expected wrapped pass rate at k=5 |
|---|---|
| Per-task Jeffreys (heterogeneous) | 0.666, interval [0.595, 0.737] |
| Pooled iid baseline | 0.759 |

The two disagree by 9.3 points, which is the diversity-efficiency
question in its sharpest form: heterogeneity says most remaining
failures are hard tasks that more samples will not rescue; the pooled
model says failures are homogeneous coin flips. They cannot both be
right at k=5.

## Adjudication rule, frozen now

When a live wrapped best-of-5 run of `ollama:telos-coder-14b` on the
hard_v2 lane completes (same oracle hash
`0b898a620223a06eeeee4244bd6e6935c53eecd4b742d9d220bdd5a96d91a89d`),
score BOTH pre-registered models by absolute error against the
measured wrapped pass rate. Whichever errs more is the falsified one.
No narrative rescue for either; a miss by both is two falsifications,
not a draw. The run must be hard_v2, not hard_v3: the forecast is
pinned to the judge that produced its evidence.

This is the quadrant the agent-reliability dossier found unclaimed:
a measured per-model diversity profile paired with a sealed,
content-addressed forecast for an unrun bench. The 3b equivalent
awaits its first per-task-vector run; the older 3b artifacts predate
the outcome vectors and cannot honestly seed a forecast.

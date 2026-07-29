# Benchmarks

Every number on this page ships with the JSON artifact it came from, in the
[benchmarks/](benchmarks/) folder of this repo, and can be re-run against the
exact GGUF you downloaded. We report confidence intervals, not adjectives, and
we state the honest null result up front.

## The headline, stated honestly

**We do not claim a capability uplift over the base model.** On our hard set,
verified inference scores 10 points above single-shot, but the 95% interval on
that difference is [-0.236, +0.420], which includes zero, and plain best-of-4
sampling ties it.

**And as of 2026-07-26 that comparison is retired for a stronger reason than a
wide interval: it was never a comparison.** Our benchmark ran the baseline as one
attempt and the treatment as several, where the treatment's first attempt is the
same call as the baseline's only attempt. The treatment therefore cannot score
lower, and across all thirteen runs we ever made there is not a single task the
baseline passed and the treatment failed. Not one. That is the signature of one
arm containing the other, not of an effect. The quantity we actually measured is
*verified pass@k*, which is a useful engineering number and is not uplift, and
every internal uplift figure we ever produced is void as a comparison for the
same reason.

A second observation, with the explanation still open. In one run, four tasks
failed in the baseline and passed in the treatment **on the treatment's first
attempt**, which is nominally the identical call. Either temperature-0 generation
is not reproducible on this instrument, or transient generation failures were
being recorded as model failures. We found a defect that would produce exactly
the second: the benchmark caught generation errors and silently retried, so in
the baseline arm, which has only one attempt, a dropped connection was published
as a task the model got wrong. That is fixed, and generation failures are now
recorded, attributed to the harness, and excluded from the denominator. The
artifacts written before 2026-07-26 do not carry the field, so we cannot tell
retrospectively which explanation applies to those four tasks. We are not going
to guess: the rebuilt measurement records it, and we will say which it was.

We are rebuilding the measurement so the baseline and the treatment are drawn
from one cached pool of independent attempts, with a compute-matched arm that
selects at random instead of using the verifier. If the verifier earns nothing
over random selection at the same compute, that is the result we will publish.

What we can state with evidence today: the model completes real coding tasks
locally, every accepted answer carries a re-checkable receipt, and reruns at
temperature 0 are byte-identical for the shipped GGUF.

## Baseline set: 8 everyday coding tasks

Single deterministic attempt per task (temperature 0).

| Arm | Passed | Wilson 95% CI |
|---|---|---|
| single-shot | 8 / 8 (100%) | [0.676, 1.000] |
| verified inference | 8 / 8 (100%) | [0.676, 1.000] |
| best-of-4 | 8 / 8 (100%) | [0.676, 1.000] |
| single + oracle | 8 / 8 (100%) | [0.676, 1.000] |

All arms saturate: these tasks are within the model's comfortable range, which
is why the hard set below exists.

## Hard set: 10 contract-heavy tasks

Tasks with edge-case-dense hidden tests (exact exception messages, tie-break
rules, boundary semantics), designed to sit at the model's frontier.

| Arm | Passed | Wilson 95% CI |
|---|---|---|
| single-shot | 8 / 10 (80%) | [0.490, 0.943] |
| verified inference | 9 / 10 (90%) | [0.596, 0.982] |
| best-of-4 | 9 / 10 (90%) | [0.596, 0.982] |
| single + oracle | 8 / 10 (80%) | [0.490, 0.943] |

Difference (verified inference vs single-shot): +0.100, 95% CI [-0.236, +0.420]
by the Newcombe unpaired approximation. The interval includes zero, so no
uplift is claimed.

## What is coming

A 110-task curated hard lane now exists (every task admitted through automated
soundness gates, with a hidden-test falsifier proving each task can fail).
Screening the released model against it shows a 44% single-attempt pass rate,
which means the next evaluation finally has statistical room for a real
answer to the uplift question. Those results will appear here when they exist,
not before.

## The public suite result, which is negative

We ran a 164-task public code-completion suite on 2026-07-09, paired, pass@1
greedy at temperature 0, the same harness for both arms. **Continued pretraining
did not improve general code completion, and the result is not significant.**

| Arm | Passed | pass@1 |
|---|---|---|
| Base `Qwen2.5-Coder-14B-Instruct` | 141 / 164 | 85.98% |
| This model, after continued pretraining | 136 / 164 | 82.93% |

- Difference: **-3.05 points**, 95% interval on the paired difference
  **[-8.76, +2.66]**, which includes zero
- Discordant pairs: 9 tasks this model gets right that the base does not, 14 the
  base gets right that this model does not, 127 both right, 14 both wrong
- McNemar: chi-square with continuity correction 0.696, exact two-sided binomial
  p = **0.405**. Not significant at 0.05

Read plainly: domain continued pretraining on one development ecosystem bought
nothing measurable on general code completion, and did not measurably harm it
either. The effective sample size for this comparison is the **23 discordant
pairs**, not 164, which is why the interval is as wide as it is. An effect
smaller than roughly 5 points was never detectable at this n.

An earlier version of this page said the public suites had not been run. That was
wrong, and it was wrong in the worst direction: the one unfavourable result was
the one missing from the benchmark page. Both arms' per-task records and the
paired comparison are in [benchmarks/](benchmarks/), with the recomputation in
[benchmarks/README.md](benchmarks/README.md) so you can check the statistics
rather than take them from us.

**One defect in this result, stated because it is ours.** The base control arm is
recorded by name, `ollama:qwen2.5-coder:14b-instruct-q4_K_M`, and not by weight
digest. Our most trustworthy number therefore rests on a control model we cannot
currently identify byte for byte. We are publishing a name to digest resolution
table to close that.

## Still not on this page

MBPP and LiveCodeBench have not been run, so no number from either is implied.
Everything above is small-N, single-run, and published with its interval
precisely so you can weigh it accordingly. None of these intervals contain a
between-seed variance component, because each figure comes from one run.

## Re-run it yourself

Determinism receipt: `llama-completion` at temperature 0, seed 7, produces
byte-identical output across reruns (output SHA-256
`970af540244384407918aa3b0172b403c24d17800e3c514c3c19937d88c7e636`).

The artifacts in [benchmarks/](benchmarks/) record every arm, count, and
interval on this page. The evaluation harness that produced them is the
Flywheel verified-inference engine; each accepted answer carries a receipt an
outside observer can re-check.

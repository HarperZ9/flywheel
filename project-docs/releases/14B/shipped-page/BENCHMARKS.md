# Benchmarks

Every number on this page ships with the JSON artifact it came from, in the
[benchmarks/](benchmarks/) folder of this repo, and can be re-run against the
exact GGUF you downloaded. We report confidence intervals, not adjectives, and
we state the honest null result up front.

## The headline, stated honestly

**We do not claim a capability uplift over the base model.** On our hard set,
verified inference scores 10 points above single-shot, but the 95% interval on
that difference is [-0.236, +0.420], which includes zero, and plain best-of-4
sampling ties it. What we can state with evidence: the model completes real
coding tasks locally, every accepted answer carries a re-checkable receipt, and
reruns at temperature 0 are byte-identical.

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

## Not on this page

We have not yet run public leaderboard suites (HumanEval, MBPP, LiveCodeBench).
Until we do, no leaderboard number is implied. The measurements above are
internal, small-N, and published with their intervals precisely so you can
weigh them accordingly.

## Re-run it yourself

Determinism receipt: `llama-completion` at temperature 0, seed 7, produces
byte-identical output across reruns (output SHA-256
`970af540244384407918aa3b0172b403c24d17800e3c514c3c19937d88c7e636`).

The artifacts in [benchmarks/](benchmarks/) record every arm, count, and
interval on this page. The evaluation harness that produced them is the
Flywheel verified-inference engine; each accepted answer carries a receipt an
outside observer can re-check.

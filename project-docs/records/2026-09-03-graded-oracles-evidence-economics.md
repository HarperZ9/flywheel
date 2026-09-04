# Graded oracles: three benchmarks that measure what a user pays for

The 2026-09-03 head-to-head could score four of fourteen tasks, and each of those
four answered one question: pass or fail. Across five provider roles that renders
as five bars with no distance between them. A reader choosing a harness cannot
act on it, and neither can a chart.

This record covers the three benchmarks added to close that, the contract change
that makes them chartable, and the properties that make each one worth running.

## The contract change

A checker used to return a list of failure codes. It may now return
`(failure_codes, metrics)` instead. The dispatcher in
`harness/cross_harness_oracles.py` unpacks either shape, so the four original
checkers are untouched and the gate is unchanged: any shortfall is still a
failure.

The metrics carry the position behind the verdict. One rounded number and a
wholly invented report both fail. Only the metric says one was four fifths right
and the other was not.

## What the three measure, and the cost each one stands for

| benchmark | question | the cost when a harness gets it wrong |
| --- | --- | --- |
| `evidence_bound_reporting/v1` | does every reported number carry its evidence, and does the run say `unverifiable` when the evidence is absent | a number that cannot be sourced is repeated downstream as fact |
| `contradiction_detection/v1` | does the run notice when its own sources disagree, and does it invent disagreements | a shipped release whose sources disagree, or a review of conflicts that were never there |
| `budgeted_evidence_selection/v1` | under a fixed budget, how much of the reachable value does the run actually capture | tokens and dollars spent on evidence that buys nothing |

Metrics reported per provider role:

- `measurement_fidelity`, `unsupported_claim_recall`, `supported_claim_precision`,
  and their mean `evidence_bound_score`
- `pair_recall`, `pair_precision`, `false_pair_count`, `trap_pairs_reported`
- `value_ratio`, `spend_usd`, `budget_overrun_usd`, `wasted_spend_usd`

All are rates or dollars, so they chart as curves rather than as bars.

## Why each fixture discriminates

A benchmark whose careless answer scores what its careful answer scores measures
nothing, so each fixture is held to a property by a test.

**Evidence-bound claims.** Five measurements taken from the real
`hh-focused-20260903-194505` run, each with its numerator, denominator and Wilson
interval. Eight claims, of which three are traps: a total cost the fixture never
states, a comparison between two harnesses the run cannot support, and a causal
account of why attempts failed. A run that marks all eight supported scores
`supported_claim_precision` 5/8 and `unsupported_claim_recall` 0.

**Source contradiction records.** Ten records over shared fields. Four pairs
genuinely contradict. Three are traps in two flavors: pairs that state the same
field with the same value, and pairs that never share a field at all. The truth
set is not hand-listed. A test derives it from the records by brute force and
fails if the fixture disagrees with itself, which is how an earlier version that
would have punished a correct answer was caught.

**Budgeted evidence pool.** Eight items against a budget of 1.00 USD. Taking the
densest item that still fits reaches 69 of the 100 points the budget can buy, and
a test asserts that gap. One item carries zero value, so spend that buys nothing
is measurable rather than inferred. The optimal answer is recomputed inside the
oracle by exact 0/1 knapsack over integer cents, so a score never depends on the
machine that produced it.

## What moved

```
declared:      14 -> 17
provisionable: 14 -> 17
scorable:       4 ->  7
```

Verdict stays `TASK_SET_PARTIAL`. Ten tasks still declare no checker.

## What this does not prove

- Three benchmarks with in-tree fixtures are not a measurement of any harness.
  No run has produced a score against them yet.
- A fixture drawn from one run carries that run only. The evidence-bound fixture
  quotes `hh-focused-20260903-194505`, whose denominator was 70 attempts across
  five roles with one repetition each.
- `value_ratio` measures selection under a stated budget. It says nothing about
  whether the items in the pool were worth buying in the first place.
- The metrics are comparable across roles on the same fixture and are not
  comparable across fixtures. They share no unit.
- Scorable is not scored. Seven of seventeen tasks can now be read. Whether a
  provider answers them well is a separate question a run has to settle.

## Reproduce

```bash
python -m pytest tests/test_cross_harness_checkers.py tests/test_task_set_executability.py -q
python scripts/run_task_set_executability.py --markdown-out task_set_executability.md
```

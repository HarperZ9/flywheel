# Graded metric report

- attempts: 35
- launched: 35
- scored: 11
- graded checkers reporting: 6

## Efficiency by role

| role | launched | scored | launch rate | readable rate | median ms | cost usd | cost coverage |
| --- | --- | --- | --- | --- | --- | --- | --- |
| claude_code | 7/7 | 2/7 | 1.0 | 0.2857 | 49147.0 | 0.4997 | 0.8571 |
| codex_harness | 7/7 | 4/7 | 1.0 | 0.5714 | 25814.0 | not reported | 0.0 |
| flywheel_harness | 7/7 | 4/7 | 1.0 | 0.5714 | 24270.0 | not reported | 0.0 |
| local_14b | 7/7 | 0/7 | 1.0 | 0.0 | 16817.0 | not reported | 0.0 |
| local_32b | 7/7 | 1/7 | 1.0 | 0.1429 | 240013.0 | not reported | 0.0 |

## budgeted_evidence_selection/v1

Scored attempts: 2

This checker reported no numeric evidence on these attempts.

## contradiction_detection/v1

Scored attempts: 3

| metric | better | claude_code | codex_harness | flywheel_harness |
| --- | --- | --- | --- | --- |
| failure_code_count | lower | not reported | 0.0 | 0.0 |
| false_pair_count | lower | not reported | 0.0 | 0.0 |
| pair_precision | higher | not reported | 1.0 | 1.0 |
| pair_recall | higher | not reported | 1.0 | 1.0 |
| trap_pairs_reported | lower | not reported | 0.0 | 0.0 |

## evidence_bound_reporting/v1

Scored attempts: 2

| metric | better | codex_harness | flywheel_harness |
| --- | --- | --- | --- |
| evidence_bound_score | higher | 1.0 | 1.0 |
| fabricated_measurements | lower | 0.0 | 0.0 |
| failure_code_count | lower | 0.0 | 0.0 |
| measurement_fidelity | higher | 1.0 | 1.0 |
| supported_claim_precision | higher | 1.0 | 1.0 |
| unsupported_claim_recall | higher | 1.0 | 1.0 |

## index_fallback_integrity/v1

Scored attempts: 1

| metric | better | claude_code |
| --- | --- | --- |
| failure_code_count | lower | 0.0 |

## paired_friction/v1

Scored attempts: 2

| metric | better | codex_harness | flywheel_harness |
| --- | --- | --- | --- |
| failure_code_count | lower | 0.0 | 1.0 |

## shared_task_artifact/v1

Scored attempts: 1

| metric | better | local_32b |
| --- | --- | --- |
| failure_code_count | lower | 1.0 |

## What this does not prove

- A mean over one repetition is a reading, not an estimate. No interval is reported because none is earned at this sample size.
- Cost covers the attempts whose provider stated a cost. A role with no cost coverage is not cheaper, it is unmeasured.
- Latency is wall clock on one machine and includes local model load time.
- A role that never returned a readable result has no quality numbers here, which is a fact about this run and not a score of zero. Why an attempt went ungraded is reported beside it, because a malformed answer and a missing one are different failures.
- An envelope found inside a refused answer was still refused, and no checker graded it. That it was there says the harness produced an answer, and it does not say the answer was right.
- The graded metrics come from in-tree fixtures. They measure a harness against those tasks and not against a customer workload.
- The run raised before sealing, so nothing ever checked that the source tree still matched the commit these rows name. The attempts each verified their own workspace, which is a narrower claim.

# Decision record: the monitor-outcome sidecar (G3, interim)

Status: **interim self-review.** The author of the code wrote this record. It is
not the independent review G3 asks for, and it says so wherever that matters.
Dates are PDT.

## Decision, owner, baseline

- **Decision.** Should Flywheel read Control Tower monitor scores beside
  independently checked task outcomes through `harness/monitor_outcome*.py`, and
  may anything be claimed about monitoring utility?
- **Owner.** The operator. Merging and any external use are operator actions.
- **Baseline.** `harness.inspect_evidence` unchanged. Run on all three Control
  Tower monitor shapes, it accepts each and keeps the score value as a flat
  `{scorer, value}` pair. It drops the per-action metadata, cannot tell a monitor
  from a task grader, and marks every sample `semantic_verification:
  UNVERIFIABLE`. That last part is correct and stays.
- **Change trigger, declared before evaluation.** Adopt the sidecar as a
  reading path if it (a) keeps scored, unscored, absent, draft and unsupported
  apart on every format, (b) refuses a declared format the log header
  contradicts, (c) never reads an outcome from the log as verified, and (d)
  keeps excluded samples in the denominator. Claim monitoring utility only after
  the study below runs on permitted real traces.

## Result so far

Criteria (a) to (d) are met on fixtures built from Control Tower's writers at
`1cc91b7`: 58 tests across the three monitor test files, and a mutation run in
which 15 reintroduced defects were all caught. The source check that forced the
rewrite is in `MONITOR-OUTCOME-SOURCE-CHECK-2026-09-23.md`.

Effectiveness is **unmeasured**. Only synthetic fixtures exist, and the bundle's
rule applies: fixture evidence does not estimate monitoring utility. No real
Control Tower log has been read.

## Pre-declared study, for when permitted traces exist

Declared now so the numbers cannot shape the design afterwards.

- **Data.** Permitted traces only, with an independent outcome label per
  sample from a checker that does not read the log's grader, and the checker's
  own identity and method recorded.
- **Split.** Samples are assigned to calibration or held-out halves by a hash of
  `(task id, sample id, epoch)` before any monitor value is read. Thresholds are
  fitted on calibration only.
- **Review budget.** A fixed fraction of samples, ranked by the declared
  aggregation (maximum over scored, executed actions), is sent to review. The
  fraction is fixed before the held-out half is opened; 5% and 20% are the
  pre-declared operating points.
- **Baselines.** Always-low, always-high and a seeded random ranking, each at the
  same budget.
- **Reported, per operating point.** Independently wrong outcomes inside and
  outside the reviewed set, with Wilson 95% intervals; the unscored, absent,
  draft and excluded counts; cost coverage where the log carries it.
- **Stop rule.** Fewer than 30 independently wrong outcomes in the held-out half
  means the result is reported as insufficient to estimate, with its counts and
  no rate.
- **Out of scope here.** Adversarial evaluation against a policy trying to
  evade the monitor (Control Tower's safety curves). That is the measurement
  monitor quality needs, and this study does not replace it.

## Decision

Retain the sidecar as a supported reading path and put it up for review. Claim
nothing about monitoring utility. The next experiment waits on an operator
decision about data (below).

## Independent recheck

- Done, by an agent on a different model with no prior context, 2026-09-23
  07:39 to 07:40 UTC: a fresh clone of `ab911f5af`, following only
  `docs/MONITOR-OUTCOME-DEMO.md`. Verdict: replayed as documented. The source
  hash matched byte for byte; all nine rows and every summary count matched; the
  three test files reported 59 passed; elapsed about 1.6 minutes. Friction it
  found, all fixed in the next commit: a Windows clone into a long directory
  fails on the repository's deeply nested artifact paths (the guide now gives
  the fix; the paths themselves are a separate cleanup task); the guide did not
  say what to do when `python` is older than 3.11; one row cited a draft score
  the output did not print (it prints it now), and the `--json` output had no
  described content.
- This is an agent replay. It shows the guide is sufficient to reproduce the
  result. It does not show that a human reviewer finds the demo clear.
- Not done: review by a person who did not write the code.

## Operator decisions this depends on

1. Whether to download the 704 MB `sample.jsonl` from the CC-BY-4.0 Hugging Face
   mirror of LinuxArena runs to extract one attributed monitor-rerun record. It
   is a Control Tower JSONL export, not an Inspect log, so it needs a small
   adapter; its manifest flags connection-string hits to scan first.
2. Whether Control Tower monitor-run `.eval` files on the LinuxArena data site
   may be read at all. They are public but carry no license statement.
3. Whether to ask the LinuxArena maintainers for terms, which would be outreach
   and is not authorized by the bundle.

## Unresolved limits

- Shapes are pinned to one revision of a format that changed twice that week.
- Live eval1 protocols also keep discarded proposals' scores in message
  metadata. No adapter reads them; whether they are in scope is open.
- The older MonitorResult overlay shape is covered by no adapter.
- Legacy folds from some writers index only monitor-visible actions, so their
  indices may not be executed-action indices. The record marks this per action.

# G4 pre-registration: the shipped hard benchmark, rerun with a held-out decider

Written 2026-10-02 before any run below.

## Decision, owner, change trigger
- Decision: what the Flywheel 1.3.0 release notes say about accuracy uplift on the shipped
  benchmark. Owner: Flywheel 1.3.0 build.
- Trigger: the notes may state a measured accuracy difference only if the paired bootstrap 95%
  interval of (search held-out pass rate minus single held-out pass rate) on the PRIMARY set
  excludes zero. Otherwise the notes keep the statement that no accuracy uplift is measured on the
  shipped benchmark, and give the interval.

## Sets
- PRIMARY: the 10-task shipped hard set (harness/tasks_hard.py HARD_REGISTRY), the set behind the
  recorded null (8/10 vs 9/10, interval [-0.236, +0.420], since retired as void because its arms
  were nested).
- SECONDARY: tasks/curated/hard_v2.jsonl (110 tasks). Reported, does not move the trigger.

## Method
Model ollama:flywheel-local-coder-14b served by an ollama serve process this workstream starts on
127.0.0.1:11500 and stops by PID. Each task's tests split in file order: 1st, 3rd, ... visible;
2nd, 4th, ... held out. A task with fewer than two tests, or whose reference solution fails either
half, is excluded and reported. Arms through run_loop (witness off): single (temperature 0, one
attempt, scored on held-out tests) and search (temperatures 0.0, 0.4, 0.8, 1.1; visible picks the
first pass; held-out decides once). Also recorded: whether the self-scored path would have
accepted, and its false accepts (visible pass, held-out fail).

## Metrics
Held-out pass rate per arm with Wilson 95%; paired bootstrap 95% (10,000 resamples, seed 7) on the
difference; self-scored false-accept share with Wilson 95%.

## Limits stated in advance
n = 10 on the primary set cannot resolve small effects. One model, one run, no seed variance
component. Splitting the hidden tests halves each suite, so both arms face weaker checks than the
original benchmark.

Script: run_heldout_rerun.py (SHA-256 below), identical to scripts/run_heldout_rerun.py on branch
claude/130-heldout-rerun.

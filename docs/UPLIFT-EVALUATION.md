# Evaluating workflow uplift

An operator needs to know whether a workflow improves completed tasks at an
acceptable cost. A retry advantage alone does not answer that question.

## What the legacy diagnostic establishes

`harness/uplift_bench.py` compares one attempt with up to several attempts. The
wrapped arm uses the same oracle to select and score its candidate. Generation
budgets differ, so its rate difference does not isolate Flywheel's contribution.
The historical independent-proportions interval also does not account for
pairing on tasks. A separated interval cannot repair either design problem.

New runs and the read-only `GET /api/uplift` interpretation report
`claim_status: not_established`. Old artifact bytes remain untouched. A stored
interval survives as `legacy_reported_interval` for audit; the canonical
`newcombe_95` and `includes_zero` are null. The native client treats v1 records
as diagnostics even when reading an older gateway.

Conditional pass rate counts only graded candidates. Confirmed completion uses
all assigned tasks: one pass and three unverified tasks means 25% confirmed
completion, even when conditional pass rate is 100%. Missing historical task
denominators stay unknown. Neither metric establishes a causal uplift claim.

The legacy runner remains available for diagnosis. This command consumes model
compute and executes the selected task tests:

```bash
python scripts/run_uplift_live.py --providers endpoint:MODEL --max-tasks 1 --out /path/to/private/report.json --work-root /path/to/private/task-work
```

Replace the endpoint, model, and paths with your configuration. Without
`--work-root`, task work is created beside the report. Without `--out`, the
report and task work default to `artifacts/uplift/` in the checkout. The task
limit applies before materialization. Malformed and duplicate task records
within the selected scope fail rather than silently reducing its denominator.

## Use the existing candidate pools

`harness/pool.py` generates a fixed number of candidates without stopping when
one passes. `harness/pool_arms.py` can compare selection policies over that same
pool. A generation-matched comparison uses these existing functions:

```python
from harness.pool_arms import best_of_k, paired, random_of_k

control = random_of_k(pool, final_score, seed=42)
treatment = best_of_k(pool, selection_check, score=final_score)
comparison = paired(control, treatment)
```

The caller supplies the pool and scoring functions. Separate callable names
do not establish independent ground truth. Audit test independence and task
coverage; never expose final scoring feedback to candidate selection. Include
selection cost, failed generations, and all-task completion alongside the
conditional candidate scores. `paired` refuses the explicitly self-scored
selection mode and uses discordant task outcomes for its test.

The existing offline driver is narrower than a general coding benchmark:

```bash
python scripts/compute_arms.py --pool-root /path/to/pool --journal /path/to/confirmatory-journal.jsonl --out /path/to/analysis
```

It supports the preregistered certificate families and requires completed run
journals. It refuses interim analysis. Do not use arbitrary coding pools with
this driver or describe its certificate results as coding workflow uplift.

## What remains to establish useful uplift

The live diagnostic requires a new work directory. It rejects existing paths,
nonportable task or candidate names, and task names that collide ignoring case
before creating task files. Custom task definitions contain executable tests
and oracle commands; use trusted definitions. This path validation does not
sandbox test execution or protect against a concurrent filesystem attacker.

A coding experiment needs development tests for selection and separate final
tests that check the user's requirements, including plausible wrong solutions.
Preregister tasks, budgets, endpoints, scoring, failure handling, repetitions,
and the decision threshold. Preserve a held-out evaluation set after tuning.

When workflows change prompts, tools, or generated candidates, a shared pool
cannot measure the full intervention. Compare the actual workflows under
matched resource limits, balance run order, and record model digests, context,
quantization, cache state, tool failures, latency, and resource use. Report
quality and completion with uncertainty and costs; preserve negative results.

This repair provides honest diagnostics and points to existing measurement
tools. It does not implement that coding experiment or establish model uplift.

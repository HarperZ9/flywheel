# METR terminal-state runs

`metr_terminal_state_runs` is a dependency-free METR Task Standard environment
for classifying agent-run receipts without corrupting the quality denominator.
It enumerates all 324 combinations of five terminal-state fields and awards
credit only when both the terminal verdict and denominator membership are
correct.

The classification order separates task quality from launch and provider
failures. Blocked, unlaunched, timed-out, rejected, malformed, and
oracle-absent runs stay out of the quality denominator. Returned runs with a
verified or refuted terminal state enter it.

## TaskFamily

```python
from metr_terminal_state_runs import TaskFamily

tasks = TaskFamily.get_tasks()
score = TaskFamily.score(
    tasks["run_000"],
    '{"verdict":"verified","in_denominator":true}',
)
```

The task needs no network, model call, environment variable, auxiliary VM,
judge model, credential, or mutable external state.

## Reproduce

From the repository root:

```powershell
uv run --project environments/metr_terminal_state_runs python -m pytest environments/metr_terminal_state_runs/tests -q
uv run --project environments/metr_terminal_state_runs python -m pytest environments/metr_terminal_state_runs/tests -q --task-standard-task-family-name metr_terminal_state_runs --task-standard-task-name run_000
```

The development dependency pins METR's official `task-standard` repository to
commit `03236e9a1a0d3c9f9d63f6c9e60a9278a59d22ff`, using its `python-package`
subdirectory. Runtime code uses only the Python standard library.

## Provenance

This fixture adapts the MIT-licensed `mlflow_terminal_state` environment in
this repository and an earlier unpublished adapter draft (commit
`4d834c97cc403c9b4a5933109ed473c8453f9b1a`, in no public repository). Tests independently pin the 324
task identifiers, verdict distribution, 23-record denominator, precedence
branches, strict scoring, and last-JSON behavior. `tools/check_repo_facts.py`
also runs this classifier and the `mlflow_terminal_state` scorer over all 324
records and fails when they disagree on any one.

This fixture has not been submitted to, reviewed by, accepted by, or endorsed
by METR.

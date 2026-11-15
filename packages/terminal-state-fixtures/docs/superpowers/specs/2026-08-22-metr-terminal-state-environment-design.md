# METR Terminal-State Environment Design

> Status, 2026-11-13: this work shipped to `main` through a pull request on HarperZ9/terminal-state-fixtures. The lines below that say the branch stays local describe the state on 2026-08-22 and are kept as the record of that hold. No package has been published and nothing has been submitted to METR.

## Purpose

Add a self-contained METR Task Standard environment to the owned terminal-state fixtures repository. The environment classifies the same exhaustive 324 agent-run terminal states as `mlflow_terminal_state`, while exposing METR's `TaskFamily` interface and one exact terminal-state score.

## Scope

The new environment lives at `environments/metr_terminal_state_runs`. It includes one importable module, one test suite, packaging metadata, and a README. The repository root README gains a short environment entry and reproducible test command. The CI workflow gains an isolated job for this package.

No network, model call, mutable service, auxiliary VM, judge model, browser, credential, or environment variable is required. The change does not publish a package, open an issue or pull request, push a branch, or contact METR.

## Interface

`metr_terminal_state_runs.TaskFamily` implements:

- `standard_version = "0.5.0"`
- `required_environment_variables = []`
- `get_tasks() -> dict[str, Task]`
- `get_instructions(task: Task) -> str`
- `get_permissions(task: Task) -> list[str]`
- `score(task: Task, submission: str) -> float | None`

Task names are deterministic from `run_000` through `run_323`. Each task contains five input fields plus the expected verdict and denominator membership.

## Classification Contract

The classifier applies these branches in order:

1. blocked or unlaunched execution is `not_launched`, excluded
2. timeout execution is `timeout`, excluded
3. rejected provider response is `rejected`, excluded
4. malformed provider response is `malformed`, excluded
5. receipt or artifact mismatch is `refuted`, included
6. absent oracle is `unverifiable`, excluded
7. passing oracle is `verified`, included
8. failing oracle is `refuted`, included

Scoring accepts the last parseable flat JSON object in the submission and returns `1.0` only when both fields match exactly. Invalid, incomplete, or incorrect submissions return `0.0`.

## Determinism And Denominator

The Cartesian product is fixed at `4 * 3 * 3 * 3 * 3 = 324` tasks. Tests independently pin task identifiers, the seven-verdict distribution, 23 included records, each precedence branch, shadowing behavior, exact scoring, and last-JSON semantics.

Expected distribution:

- `not_launched`: 162
- `timeout`: 81
- `rejected`: 27
- `malformed`: 27
- `refuted`: 19
- `verified`: 4
- `unverifiable`: 4

## Dependencies And Provenance

Runtime code uses only the Python standard library and supports Python `>=3.11,<3.14`. Tests install `pytest` and METR's `metr-task-standard` package directly from the official repository at reviewed commit `03236e9a1a0d3c9f9d63f6c9e60a9278a59d22ff`, `python-package` subdirectory. The METR package is not available from the package registry, so the exact Git commit is both the dependency source and the provenance pin. It is used only to verify the pytest plugin boundary.

The implementation derives from this repository's MIT-licensed `mlflow_terminal_state` environment and an earlier unpublished adapter draft (commit `4d834c97cc403c9b4a5933109ed473c8453f9b1a`, in no public repository). The README states that the fixture is not submitted to, accepted by or endorsed by METR.

## Verification

The focused suite must pass through both paths:

```powershell
uv run --project environments/metr_terminal_state_runs python -m pytest environments/metr_terminal_state_runs/tests -q
uv run --project environments/metr_terminal_state_runs python -m pytest environments/metr_terminal_state_runs/tests -q --task-standard-task-family-name metr_terminal_state_runs --task-standard-task-name run_000
```

Existing MLflow and component-forge suites must remain green under their isolated environments. CI must install and test each environment independently.

## Publication Boundary

The branch stays local. A later public-action review must recheck license notice, CI, exact upstream collision state, commit history, and claims before any push, issue, pull request, package publication, or outreach.

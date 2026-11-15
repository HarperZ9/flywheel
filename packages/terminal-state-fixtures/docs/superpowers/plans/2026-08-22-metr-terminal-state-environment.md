# METR Terminal-State Environment Implementation Plan

> Status, 2026-11-13: this work shipped to `main` through a pull request on HarperZ9/terminal-state-fixtures. The lines below that say the branch stays local describe the state on 2026-08-22 and are kept as the record of that hold. No package has been published and nothing has been submitted to METR.

**Goal:** Add an owned, deterministic 324-case METR Task Standard environment without publishing or contacting any external party.

**Architecture:** A single standard-library module implements METR's `TaskFamily` surface and exact terminal-state scorer. An independent pytest suite pins the exhaustive dataset and scorer semantics, while packaging and CI keep METR's pytest plugin in the test path only.

**Tech Stack:** Python 3.11 through 3.13, standard library, pytest, METR Task Standard pinned to official commit `03236e9a1a0d3c9f9d63f6c9e60a9278a59d22ff`, uv, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-22-metr-terminal-state-environment-design.md`

## Global Constraints

- Runtime code must use only the Python standard library.
- Supported Python range is `>=3.11,<3.14`.
- Task identifiers must be exactly `run_000` through `run_323`.
- No network, model, mutable service, auxiliary VM, judge model, credential, or environment variable is allowed.
- The branch remains local and unpublished.

---

### Task 1: TaskFamily contract and deterministic scorer

**Files:**
- Create: `environments/metr_terminal_state_runs/tests/test_environment.py`
- Create: `environments/metr_terminal_state_runs/metr_terminal_state_runs.py`

**Interfaces:**
- Consumes: the eight-branch classification contract in the design spec.
- Produces: `TaskFamily` with `classify`, `get_tasks`, `get_instructions`, `get_permissions`, and `score`.

- [ ] **Step 1: Write failing contract tests**

Create tests with literal expectations for 324 ordered task names, the exact verdict histogram, 23 included records, one case for every branch and shadowing boundary, self-contained instructions, exact Boolean scoring, invalid JSON, missing fields, last-correct JSON, and last-incorrect JSON.

- [ ] **Step 2: Verify RED**

Run:

```powershell
uv run --project environments/metr_terminal_state_runs --with pytest python -m pytest environments/metr_terminal_state_runs/tests -q
```

Expected: collection fails because `metr_terminal_state_runs` does not exist.

- [ ] **Step 3: Implement the minimal TaskFamily**

Implement the exact typed task fields, ordered classifier, Cartesian-product generator, self-contained instruction string, empty permission list, reverse last-JSON parsing, and strict two-field score.

- [ ] **Step 4: Verify GREEN**

Run the focused command from Step 2. Expected: all tests pass with zero failures.

- [ ] **Step 5: Commit**

```powershell
git add environments/metr_terminal_state_runs
git commit -m "feat: add METR terminal-state task family"
```

### Task 2: Package, plugin integration, documentation, and CI

**Files:**
- Create: `environments/metr_terminal_state_runs/pyproject.toml`
- Create: `environments/metr_terminal_state_runs/README.md`
- Modify: `environments/metr_terminal_state_runs/tests/test_environment.py`
- Modify: `README.md`
- Modify: `.github/workflows/tests.yml`

**Interfaces:**
- Consumes: `metr_terminal_state_runs.TaskFamily` from Task 1.
- Produces: editable installation, METR pytest-plugin verification, documented reproduction commands, and an isolated CI job.

- [ ] **Step 1: Add a failing installed-package and plugin-path test**

Add a `pytest.mark.task_standard_tasks(["run_000"])` test that consumes the plugin-provided `task_family`, `task_name`, and `task` fixtures and scores the literal correct terminal answer. Run with `--task-standard-task-family-name metr_terminal_state_runs --task-standard-task-name run_000` and confirm the packaging or plugin path fails before metadata exists.

- [ ] **Step 2: Add minimal packaging metadata**

Declare package name `metr-terminal-state-runs`, version `0.1.0`, Python range `>=3.11,<3.14`, no runtime dependencies, and Hatchling inclusion of `metr_terminal_state_runs.py`.

- [ ] **Step 3: Add public-safe documentation and isolated CI**

Document purpose, denominator logic, exact 324-case count, reproduction commands, provenance, non-endorsement, and no-network boundary. Update the root README environment list. Add a GitHub Actions job that installs pytest, the exact official METR Git dependency, and the editable environment before running its tests.

- [ ] **Step 4: Verify package and plugin paths**

Run both verification commands from the design spec. Expected: all tests pass, including the plugin-specific test.

- [ ] **Step 5: Run regressions**

Run the MLflow suite with `uv run --project ... --with pytest python -m pytest` and component-forge with `uv run --project ... --with pytest python -m pytest`. Expected: every suite passes with zero failures.

- [ ] **Step 6: Commit**

```powershell
git add environments/metr_terminal_state_runs README.md .github/workflows/tests.yml
git commit -m "docs: integrate METR terminal-state fixture"
```

### Task 3: Final evidence and publication hold

**Files:**
- Modify only if verification finds an exact defect in a file from Tasks 1 or 2.

**Interfaces:**
- Consumes: committed implementation and all isolated test commands.
- Produces: a clean local branch, exact commit hash, test counts, and a no-publication receipt for outreach integration.

- [ ] **Step 1: Run the full verification matrix**

Repeat the two METR commands and both regression suites from Task 2. Record exact counts and exit codes.

- [ ] **Step 2: Verify repository state**

Run `git status --short`, `git log -3 --oneline`, and a secret-pattern scan limited to changed files. Expected: clean worktree, local commits only, and zero secrets.

- [ ] **Step 3: Preserve the publication boundary**

Do not push, open an issue or pull request, publish a package, contact METR, or claim METR acceptance or endorsement.

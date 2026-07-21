# Quantum-Classical Falsifiable Lanes Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task by task.

**Goal:** Add two deterministic physics TaskSpecs that expose amplitude-closure and projection errors, then record a source-bounded research-lane map and exercise the existing receipt pipeline.

**Architecture:** Extend the existing `PHYSICS_REGISTRY`; keep candidate generation on the normal harness/gateway path and acceptance in hidden pytest oracles. The tasks compute model-independent two-branch invariants and leakage accounting, not disputed gravitational dynamics. Forum, Mneme, and Crucible remain separate existing tools connected by scratch receipts.

**Tech Stack:** Python 3.10+, stdlib complex arithmetic, pytest, existing TaskSpec/curator/gateway, Forum ledger, Mneme, Crucible.

**Spec:** `C:/dev/project-docs/specs/SPEC-QCR-FALSIFIABLE-LANES-20260721.md`

---

### Task 1: Add a branch-state entanglement invariant oracle

**Files:**
- Modify: `tests/test_tasks_physics.py`
- Modify: `harness/tasks_physics.py`

**Step 1: Write a failing registry/mutant test**

Pin a task ID `branch_entanglement_invariants`. Use `_run_with` to prove the
oracle rejects a plausible implementation that computes
`abs(a00*a11-a01*a10)` without dividing by total norm.

**Step 2: Run RED**

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest tests/test_tasks_physics.py -q -p no:cacheprovider
```

Expected: task missing or mutant test fails.

**Step 3: Add the smallest TaskSpec**

The candidate function returns `(norm2, determinant_magnitude, concurrence)` for
a nonzero finite pure two-branch state, with:

```python
norm2 = sum(abs(a) ** 2 for a in (a00, a01, a10, a11))
d = abs(a00 * a11 - a01 * a10) / norm2
return norm2, d, 2 * d
```

Reject zero norm2 and any non-finite real or imaginary amplitude component.
Hidden tests must cover a product state, Bell state, scale and local-phase
invariance, zero/non-finite input, and at least one nontrivial numeric state.

**Step 4: Run GREEN**

Use the Task 1 focused command.

### Task 2: Add a projected-sector leakage oracle

**Files:**
- Modify: `tests/test_tasks_physics.py`
- Modify: `harness/tasks_physics.py`

**Step 1: Write a failing mutant test**

Pin task ID `projected_sector_audit`. Reject a plausible implementation that
renormalizes the selected four amplitudes and reports conditional concurrence
but always reports zero leakage / unit success.

**Step 2: Run RED**

Use the Task 1 focused command.

**Step 3: Add the smallest TaskSpec**

The candidate receives a supplied amplitude sequence and four distinct ordered
indices `(i00, i01, i10, i11)` mapping exactly to
`(a00, a01, a10, a11)`. It returns
`(full_norm2, success_probability, leakage_probability,
conditional_concurrence)`. Compute `sector_norm2` and `full_norm2` separately;
success is `sector_norm2/full_norm2`, leakage is `1-success`, and conditional
concurrence is `2*abs(a00*a11-a01*a10)/sector_norm2`. Reject non-finite
amplitudes, zero full/selected norm2, duplicate indices, non-integer indices, and
out-of-range indices.

Hidden tests must cover a full Bell sector, separable selected sector with
leakage, conditionally entangled selected sector with leakage, global scale
invariance, and invalid/zero/non-finite inputs. The task verifies bookkeeping of
the supplied vector only; it must not claim that the vector contains every
physical amplitude or channel.

**Step 4: Run GREEN**

Use the Task 1 focused command.

### Task 3: Record the bounded research program

**Files:**
- Create: `docs/research/2026-07-21-quantum-classical-falsification-lanes.md`

**Step 1: Write only source-bounded claims**

Record explicit model classes, observables, nuisance variables, shared oracles,
and the six ranked lanes from the approved spec. Every claim uses three
orthogonal fields: `evidence_state`, `scope_state`, and `controversy_state`.
Include primary links
for Bose et al. (1707.06050), Marletto--Vedral (1707.06036), Aziz--Howl
(2510.19714), Yant--Blencowe (2503.20855), and the phenomenology roadmap
(2312.00409).

**Step 2: State the stop boundary**

Do not call Planck mass a direct Planck-length/energy probe. Do not install BMV
or Aziz--Howl scaling as truth. Prioritize complete amplitude closure with
same/distinct-field and full/projected-sector switches.

**Step 3: Run documentation and focused gates**

```powershell
git diff --check
python -m pytest tests/test_tasks_physics.py tests/test_task_curator.py -q -p no:cacheprovider
```

### Task 4: Bounded regression and receipt-backed dry run

**Files:**
- Create scratch receipts only under `C:/dev/scratch/qcr-2026-07-21-01/`.

**Step 1: Run the bounded local-model gate**

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest -q -p no:cacheprovider tests/test_tasks_physics.py tests/test_task_curator.py tests/test_science_bench.py tests/test_tension_ledger.py tests/test_conjecture_forge.py tests/test_lean_oracle.py tests/test_discovery_flywheel.py tests/test_gateway.py
```

**Step 2: Exercise only existing orchestration contracts**

Declare a Forum ledger-only external campaign, store/recall one source-bound lane
fact with Mneme keyword recall, export measurements with Mneme v2, and load/assess
them with Crucible. Record commands, versions, hashes, verdicts, and gaps. Do not
start WSL or a model endpoint. If no endpoint is already listening, mark model
execution blocked while retaining deterministic gate results.

**Step 3: Review and publish**

Run `git diff --check`, inspect the full diff, resolve spec/quality findings,
rerun affected exact gates, commit as `feat: add falsifiable quantum-classical
physics lanes`, push `feat/qcr-falsifiable-lanes`, open a PR, and recheck Actions.

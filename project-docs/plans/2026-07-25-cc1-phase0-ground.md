# CC-1 Phase 0 (Ground) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the floor hold before anything new is built: a four-way verdict the whole harness can carry, an oracle boundary that cannot leak the signing environment into candidate code, an unbiased advantage estimator, a training path whose group is a real policy sample, and one command that takes an existing orphan chain end to end and prints MATCH.

**Architecture:** Phase 0 changes seams, not features. A new stdlib `verdict.py` defines the vocabulary (PASS/FAIL/UNDECIDED/UNVERIFIABLE plus execution and attribution). `OracleResult` grows to carry it while keeping `passed` working for the 28 existing binary call sites and raising the moment a non-binary verdict reaches code that cannot handle it. `advantages.py` splits the estimator out of `rl_from_oracle.py` so Dr.GRPO (no std division, no length normalization) is selectable and recorded. `rl_from_oracle.collect` stops sampling its group across nine temperatures. The final task wires `matmul_oracle -> rl_from_oracle.collect -> receipt -> verify` behind `flywheel gate` and asserts MATCH. If that command cannot be made to work in one week, CC-1 is disproven cheaply and the program stops.

**Tech Stack:** Python 3.10+ stdlib only for everything in `harness/` (zero runtime dependencies is a load-bearing property: the stranger's offline verifier must run on a bare interpreter). pytest for tests. GitHub Actions for CI. No torch, no trl, no network in any Phase 0 code path.

## Global Constraints

Copied verbatim from `project-docs/specs/2026-07-25-certified-commons-design.md`:

- No receipt, no accept. No learned model on the accept path; an external oracle disposes.
- Verdicts are PASS, FAIL, UNDECIDED, UNVERIFIABLE. UNVERIFIABLE is a first-class verdict; the gap is part of the record.
- Records are append-only: repair adds on top, never rewrites.
- Receipts state what they do NOT prove.
- Ethics never sit in the accept path; criteria do: explicit, versioned, hash-pinned, forkable, contestable.
- `harness/` is stdlib-only. `train/` may use torch and peft and trl. No new runtime dependency enters `harness/` in Phase 0.
- Files in `harness/` stay under 300 lines. Existing violations are grandfathered on a burn-down list; no NEW file may exceed it and no grandfathered file may grow.
- Credentials: presence only, never the value. Keys never reach receipts, ledgers, logs, or plaintext files.
- Voice rule for all prose in code comments, docstrings, and docs: no em-dashes.
- Apache-2.0 for everything load-bearing for verification (harness, criteria, checkers, verifier, bundles, adapters).
- Posture is non-competitive: no comparison framing in any user-facing string.

**Verified repository facts this plan depends on** (re-read at HEAD `8bf1109`, branch `feat/release-32b`):

- `harness/oracle.py:50-60` defines `OracleResult` with `passed: bool` and `verdict()` returning only `"PASS"` or `"FAIL"`.
- `harness/oracle.py:33` defines `run_env()` as `{**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}` (full environment inherited).
- 28 `.passed` call sites exist across 13 modules: `calibration.py`, `companion.py`, `consensus.py`, `escalation.py`, `eval.py`, `failure_corpus.py`, `integrity.py`, `loop.py`, `oracle.py`, `quorum.py`, `rl_from_oracle.py`, `search.py`, `selector.py`.
- `harness/rl_from_oracle.py:47-60` computes `(r - mean) / (pstdev + EPS)`; `:190` calls `budget_schedule(self.group_size)`; `:197` computes `reward = 1.0 if oracle.verify(...).passed else 0.0`; `:145` declares `PolicyOptimizer` as a Protocol with zero implementations.
- `harness/matmul_oracle.py:85-104` defines `MatMulSchemeOracle` with `oracle_type = "matmul_bilinear"` and `verify(candidate, task=None) -> OracleResult`; `:122` `strassen_scheme()`; `:136` `perturb_scheme()`; `:145` `drop_triple()`; `:153` `dumps()`.
- `harness/envelope.py:47-51` `_content_preimage()` pops `verdict` from the hashed preimage, so flipping a verdict currently breaks no hash.
- `harness/gateway.py:766` `_Handler`, `:1008` `do_GET`, `:1014` `do_POST`, `:2370` binds `127.0.0.1` with no authentication.
- No `.github/workflows/` directory exists.

---

### Task 1: The verdict vocabulary

**Files:**
- Create: `harness/verdict.py`
- Test: `tests/test_verdict.py`

**Interfaces:**
- Consumes: nothing (new primitive, no imports from `harness/`)
- Produces: `Verdict` (str enum: `PASS`, `FAIL`, `UNDECIDED`, `UNVERIFIABLE`), `Execution` (str enum: `COMPLETED`, `TIMEOUT`, `CRASHED`, `RESOURCE_EXCEEDED`, `TOOLCHAIN_MISSING`, `HARNESS_ERROR`), `Attribution` (str enum: `CANDIDATE`, `HARNESS`, `ENVIRONMENT`), `UndecidedReason` and `UnverifiableReason` (str enums), `is_dispositive(verdict) -> bool`, `attribution_for(execution) -> Attribution`

- [ ] **Step 1: Write the failing test**

Create `tests/test_verdict.py`:

```python
from harness.verdict import (
    Verdict, Execution, Attribution, UndecidedReason, UnverifiableReason,
    is_dispositive, attribution_for,
)


def test_four_verdicts_exist_and_are_strings():
    assert Verdict.PASS == "PASS"
    assert Verdict.FAIL == "FAIL"
    assert Verdict.UNDECIDED == "UNDECIDED"
    assert Verdict.UNVERIFIABLE == "UNVERIFIABLE"
    assert len(list(Verdict)) == 4


def test_only_pass_and_fail_are_dispositive():
    assert is_dispositive(Verdict.PASS) is True
    assert is_dispositive(Verdict.FAIL) is True
    assert is_dispositive(Verdict.UNDECIDED) is False
    assert is_dispositive(Verdict.UNVERIFIABLE) is False


def test_candidate_attributable_executions_blame_the_candidate():
    # A candidate that loops forever or crashes the checker earned its FAIL.
    assert attribution_for(Execution.TIMEOUT) is Attribution.CANDIDATE
    assert attribution_for(Execution.CRASHED) is Attribution.CANDIDATE
    assert attribution_for(Execution.RESOURCE_EXCEEDED) is Attribution.CANDIDATE


def test_harness_and_environment_failures_never_blame_the_candidate():
    # Training on these would teach the model that our bugs are its fault.
    assert attribution_for(Execution.HARNESS_ERROR) is Attribution.HARNESS
    assert attribution_for(Execution.TOOLCHAIN_MISSING) is Attribution.ENVIRONMENT


def test_completed_execution_attributes_to_the_candidate():
    assert attribution_for(Execution.COMPLETED) is Attribution.CANDIDATE


def test_reason_enums_are_closed_vocabularies_not_free_text():
    assert UndecidedReason.HELD_OUT_DISAGREEMENT == "HELD_OUT_DISAGREEMENT"
    assert UnverifiableReason.ORACLE_UNAVAILABLE == "ORACLE_UNAVAILABLE"
    assert "OUT_OF_SCOPE" in {r.value for r in UndecidedReason}
    assert "RECEIPT_COMMIT_FAILED" in {r.value for r in UndecidedReason}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_verdict.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'harness.verdict'`

- [ ] **Step 3: Write minimal implementation**

Create `harness/verdict.py`:

```python
"""verdict.py -- the shared verdict vocabulary.

Four verdicts, not two. A boolean cannot say "the oracle decided it cannot
decide", and a system whose interface cannot carry UNVERIFIABLE cannot honestly
claim UNVERIFIABLE is first class. The gap is part of the record.

Attribution is separate from the verdict because who caused a non-completion
decides whether it teaches anything. A candidate that loops forever earned its
FAIL. A missing toolchain did not, and training on it would teach the model that
our environment's absence is its error.
"""
from __future__ import annotations

from enum import Enum


class Verdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNDECIDED = "UNDECIDED"          # the oracle ran and declined to dispose
    UNVERIFIABLE = "UNVERIFIABLE"    # the oracle could not run at all


class Execution(str, Enum):
    COMPLETED = "COMPLETED"
    TIMEOUT = "TIMEOUT"
    CRASHED = "CRASHED"
    RESOURCE_EXCEEDED = "RESOURCE_EXCEEDED"
    TOOLCHAIN_MISSING = "TOOLCHAIN_MISSING"
    HARNESS_ERROR = "HARNESS_ERROR"


class Attribution(str, Enum):
    CANDIDATE = "CANDIDATE"
    HARNESS = "HARNESS"
    ENVIRONMENT = "ENVIRONMENT"


class UndecidedReason(str, Enum):
    HELD_OUT_DISAGREEMENT = "HELD_OUT_DISAGREEMENT"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    NON_CONJUNCTIVE_RULE = "NON_CONJUNCTIVE_RULE"
    CONSENSUS_NOT_PROOF = "CONSENSUS_NOT_PROOF"
    RECEIPT_COMMIT_FAILED = "RECEIPT_COMMIT_FAILED"


class UnverifiableReason(str, Enum):
    ORACLE_UNAVAILABLE = "ORACLE_UNAVAILABLE"
    TOOLCHAIN_MISSING = "TOOLCHAIN_MISSING"
    QA_CARD_ABSENT = "QA_CARD_ABSENT"
    ENVELOPE_MISSING = "ENVELOPE_MISSING"


_CANDIDATE_EXECUTIONS = {
    Execution.COMPLETED,
    Execution.TIMEOUT,
    Execution.CRASHED,
    Execution.RESOURCE_EXCEEDED,
}

_ATTRIBUTION = {
    Execution.HARNESS_ERROR: Attribution.HARNESS,
    Execution.TOOLCHAIN_MISSING: Attribution.ENVIRONMENT,
}


def is_dispositive(verdict: Verdict | str) -> bool:
    """True iff the verdict decided the question. Only PASS and FAIL do."""
    return Verdict(verdict) in (Verdict.PASS, Verdict.FAIL)


def attribution_for(execution: Execution | str) -> Attribution:
    """Who caused this non-completion. Candidate-attributable failures are real
    FAILs and carry gradient; harness and environment failures are dropped and
    logged, never scored."""
    ex = Execution(execution)
    if ex in _CANDIDATE_EXECUTIONS:
        return Attribution.CANDIDATE
    return _ATTRIBUTION[ex]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_verdict.py -v`
Expected: PASS, 6 passed

- [ ] **Step 5: Commit**

```bash
git add harness/verdict.py tests/test_verdict.py
git commit -m "feat(verdict): four-way verdict vocabulary with attribution"
```

---

### Task 2: Widen OracleResult without breaking the 28 binary call sites

**Files:**
- Modify: `harness/oracle.py:50-66`
- Test: `tests/test_oracle_verdict_widening.py`

**Interfaces:**
- Consumes: `harness.verdict.Verdict`, `Execution`, `Attribution`, `is_dispositive`, `attribution_for` (Task 1)
- Produces: `OracleResult` with new fields `verdict_: Verdict = Verdict.PASS` (set from `passed` when not given), `execution: Execution = Execution.COMPLETED`, `attribution: Attribution = Attribution.CANDIDATE`, `raw_stdout_sha256: str = ""`, `duration_ns: int = 0`, `objective: str | None = None`; `passed` becomes a property raising `NonDispositiveVerdict` on UNDECIDED/UNVERIFIABLE; `verdict()` returns the four-way value; new exception `NonDispositiveVerdict`

**Why `passed` raises instead of returning False:** returning False would silently score an undecided rollout as a failure, which is exactly the escape hatch the design forbids. Raising surfaces every call site that needs teaching, and because every oracle shipping today produces only PASS or FAIL, no existing site can trip it.

- [ ] **Step 1: Write the failing test**

Create `tests/test_oracle_verdict_widening.py`:

```python
import pytest

from harness.oracle import OracleResult, NonDispositiveVerdict
from harness.verdict import Verdict, Execution, Attribution


def _binary(passed: bool) -> OracleResult:
    return OracleResult(passed=passed, cmd="c", output_hash="h",
                        stdout_excerpt="", rc=0 if passed else 1)


def test_existing_binary_construction_still_works():
    # The 28 call sites in 13 modules must keep working unchanged.
    assert _binary(True).passed is True
    assert _binary(False).passed is False
    assert _binary(True).verdict() == "PASS"
    assert _binary(False).verdict() == "FAIL"


def test_binary_construction_infers_the_verdict():
    assert _binary(True).verdict_ is Verdict.PASS
    assert _binary(False).verdict_ is Verdict.FAIL


def test_undecided_can_be_constructed():
    r = OracleResult(verdict_=Verdict.UNDECIDED, cmd="c", output_hash="h",
                     stdout_excerpt="", rc=0)
    assert r.verdict() == "UNDECIDED"


def test_passed_raises_on_a_non_dispositive_verdict():
    # Silently returning False here would score an undecided rollout as a
    # failure: the escape hatch the design forbids.
    r = OracleResult(verdict_=Verdict.UNVERIFIABLE, cmd="c", output_hash="h",
                     stdout_excerpt="", rc=0)
    with pytest.raises(NonDispositiveVerdict):
        _ = r.passed


def test_defaults_are_completed_and_candidate_attributed():
    r = _binary(False)
    assert r.execution is Execution.COMPLETED
    assert r.attribution is Attribution.CANDIDATE


def test_harness_error_attributes_away_from_the_candidate():
    r = OracleResult(verdict_=Verdict.UNVERIFIABLE, cmd="c", output_hash="h",
                     stdout_excerpt="", rc=1,
                     execution=Execution.HARNESS_ERROR)
    assert r.attribution is Attribution.HARNESS


def test_constructing_with_neither_passed_nor_verdict_is_an_error():
    with pytest.raises(ValueError):
        OracleResult(cmd="c", output_hash="h", stdout_excerpt="", rc=0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_oracle_verdict_widening.py -v`
Expected: FAIL with `ImportError: cannot import name 'NonDispositiveVerdict' from 'harness.oracle'`

- [ ] **Step 3: Write minimal implementation**

In `harness/oracle.py`, add to the imports at the top (after `from .task import Task`):

```python
from .verdict import Verdict, Execution, Attribution, is_dispositive, attribution_for
```

Replace the whole `OracleResult` dataclass and its `verdict()` method (currently `harness/oracle.py:49-60`) with:

```python
class NonDispositiveVerdict(Exception):
    """Raised when boolean truth is asked of a verdict that did not decide.

    Returning False here would score an UNDECIDED rollout as a failure, which
    teaches the policy that breaking the verifier is as good as failing it. The
    caller must handle the four-way verdict instead.
    """


@dataclass
class OracleResult:
    cmd: str
    output_hash: str
    stdout_excerpt: str
    rc: int
    verdict_: Verdict | None = None
    execution: Execution = Execution.COMPLETED
    attribution: Attribution | None = None
    raw_stdout_sha256: str = ""
    duration_ns: int = 0
    objective: str | None = None
    _passed: bool | None = field(default=None, repr=False)

    def __init__(self, cmd: str, output_hash: str, stdout_excerpt: str, rc: int,
                 passed: bool | None = None, verdict_: Verdict | str | None = None,
                 execution: Execution | str = Execution.COMPLETED,
                 attribution: Attribution | str | None = None,
                 raw_stdout_sha256: str = "", duration_ns: int = 0,
                 objective: str | None = None):
        if passed is None and verdict_ is None:
            raise ValueError("OracleResult needs either passed= or verdict_=")
        self.cmd = cmd
        self.output_hash = output_hash
        self.stdout_excerpt = stdout_excerpt
        self.rc = rc
        self.execution = Execution(execution)
        if verdict_ is not None:
            self.verdict_ = Verdict(verdict_)
        else:
            self.verdict_ = Verdict.PASS if passed else Verdict.FAIL
        self.attribution = (Attribution(attribution) if attribution is not None
                            else attribution_for(self.execution))
        self.raw_stdout_sha256 = raw_stdout_sha256
        self.duration_ns = duration_ns
        self.objective = objective

    @property
    def passed(self) -> bool:
        """Binary truth, for the call sites that predate the four-way verdict.
        Raises rather than lying when the verdict did not decide."""
        if not is_dispositive(self.verdict_):
            raise NonDispositiveVerdict(
                f"verdict is {self.verdict_.value}; handle it explicitly "
                f"(attribution={self.attribution.value})")
        return self.verdict_ is Verdict.PASS

    def verdict(self) -> str:
        return self.verdict_.value
```

Add `field` to the dataclasses import line at the top of the file, so it reads:

```python
from dataclasses import dataclass, field
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_oracle_verdict_widening.py -v`
Expected: PASS, 7 passed

- [ ] **Step 5: Run the reverse-import slice to prove no regression**

Run: `python -m pytest tests/test_oracle.py tests/test_loop.py tests/test_selector.py tests/test_search.py tests/test_escalation.py tests/test_consensus.py tests/test_calibration.py tests/test_matmul_oracle.py tests/test_rl_from_oracle.py -q`
Expected: PASS, no failures. If any test fails on a keyword argument, the fix is at the call site: `OracleResult(passed=..., ...)` still works, positional construction does not.

- [ ] **Step 6: Commit**

```bash
git add harness/oracle.py tests/test_oracle_verdict_widening.py
git commit -m "feat(oracle): carry the four-way verdict, attribution, and raw hash"
```

---

### Task 3: Close the oracle environment boundary

**Files:**
- Modify: `harness/oracle.py:33` (`run_env`)
- Test: `tests/test_oracle_env_boundary.py`

**Interfaces:**
- Consumes: nothing new
- Produces: `run_env(extra: dict | None = None) -> dict` returning a deny-by-default allowlist; module constant `ENV_ALLOWLIST: frozenset[str]`

**Why:** `run_env()` currently hands the entire process environment to a subprocess that executes model-written code. Every secret the operator has exported, and later the receipt signing key, sits inside that blast radius. Phase 0 closes it before any key exists to steal.

- [ ] **Step 1: Write the failing test**

Create `tests/test_oracle_env_boundary.py`:

```python
import os

from harness.oracle import run_env, ENV_ALLOWLIST


def test_a_secret_in_the_parent_environment_does_not_reach_the_child(monkeypatch):
    monkeypatch.setenv("FLYWHEEL_SIGNING_KEY", "s3cret")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-live-do-not-leak")
    env = run_env()
    assert "FLYWHEEL_SIGNING_KEY" not in env
    assert "OPENAI_API_KEY" not in env
    assert "s3cret" not in "".join(env.values())


def test_the_interpreter_still_works(monkeypatch):
    # PATH and the platform loader variables must survive or pytest cannot run.
    env = run_env()
    assert "PATH" in env
    assert env["PYTHONDONTWRITEBYTECODE"] == "1"
    if os.name == "nt":
        assert "SYSTEMROOT" in env


def test_allowlist_is_deny_by_default(monkeypatch):
    monkeypatch.setenv("SOME_FUTURE_VARIABLE_NOBODY_ANTICIPATED", "x")
    assert "SOME_FUTURE_VARIABLE_NOBODY_ANTICIPATED" not in run_env()
    assert "SOME_FUTURE_VARIABLE_NOBODY_ANTICIPATED" not in ENV_ALLOWLIST


def test_caller_can_add_explicit_extras():
    env = run_env({"FLYWHEEL_TASK_ID": "t1"})
    assert env["FLYWHEEL_TASK_ID"] == "t1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_oracle_env_boundary.py -v`
Expected: FAIL. `test_a_secret_in_the_parent_environment_does_not_reach_the_child` fails because `run_env()` returns `{**os.environ, ...}`; the `ENV_ALLOWLIST` import also fails.

- [ ] **Step 3: Write minimal implementation**

Replace `harness/oracle.py:33-34` (`def run_env(): return {**os.environ, ...}`) with:

```python
# Deny by default. The oracle subprocess executes model-written code, so every
# variable that crosses this boundary is a variable an adversarial candidate can
# read. Add only what an interpreter needs to start.
ENV_ALLOWLIST = frozenset({
    "PATH", "HOME", "USER", "LANG", "LC_ALL", "TZ", "TMPDIR",
    "PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV",
    # Windows loader variables: without these, python.exe does not start.
    "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT",
    "TEMP", "TMP", "USERPROFILE", "APPDATA", "LOCALAPPDATA",
    "PROCESSOR_ARCHITECTURE", "NUMBER_OF_PROCESSORS",
})


def run_env(extra: dict | None = None) -> dict:
    """The child's environment: an allowlist, never an inheritance.

    A secret exported in the operator's shell must not be readable by a
    candidate the model wrote. `extra` is the explicit, auditable way to pass
    something in.
    """
    env = {k: v for k, v in os.environ.items() if k in ENV_ALLOWLIST}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if extra:
        env.update(extra)
    return env
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_oracle_env_boundary.py -v`
Expected: PASS, 4 passed

- [ ] **Step 5: Prove the oracle still runs real subprocesses**

Run: `python -m pytest tests/test_oracle.py tests/test_oracle_hostile_candidate.py -q`
Expected: PASS. If a test fails because a needed variable was denied, add that variable to `ENV_ALLOWLIST` with a one-line comment saying why it is safe, and re-run. Do not widen the allowlist to `os.environ`.

- [ ] **Step 6: Commit**

```bash
git add harness/oracle.py tests/test_oracle_env_boundary.py
git commit -m "fix(oracle): deny-by-default environment allowlist for candidate execution"
```

---

### Task 4: Unbiased advantages, selectable and recorded

**Files:**
- Create: `harness/advantages.py`
- Modify: `harness/rl_from_oracle.py:44-60` (delete `grpo_advantages`, re-export from the new module)
- Test: `tests/test_advantages.py`

**Interfaces:**
- Consumes: nothing
- Produces: `advantages(rewards: list[float], estimator: str = "drgrpo") -> list[float]`; `ESTIMATORS: frozenset[str]` = `{"drgrpo", "grpo_std"}`; `AdvantageConfigError`
- `harness.rl_from_oracle.grpo_advantages` keeps working as a thin alias for `advantages(rewards, "grpo_std")` so existing tests and callers do not move in this task.

**Why:** dividing by the group standard deviation makes a group's gradient magnitude depend on how mixed that group happened to be, which biases learning toward medium-difficulty groups for reasons unrelated to their content. Dr.GRPO drops the division. Keeping the old estimator selectable makes it a control arm rather than dead code.

- [ ] **Step 1: Write the failing test**

Create `tests/test_advantages.py`:

```python
import pytest

from harness.advantages import advantages, ESTIMATORS, AdvantageConfigError


def test_drgrpo_is_mean_centred_with_no_std_division():
    # Two groups with identical structure but different spread must produce
    # advantages that differ in magnitude, not identical normalized values.
    tight = advantages([0.0, 1.0], "drgrpo")
    assert tight == [-0.5, 0.5]


def test_drgrpo_magnitude_tracks_the_actual_reward_gap():
    small_gap = advantages([0.4, 0.6], "drgrpo")
    big_gap = advantages([0.0, 1.0], "drgrpo")
    assert abs(big_gap[1]) > abs(small_gap[1])


def test_grpo_std_normalizes_both_groups_to_the_same_scale():
    # The legacy estimator erases the gap difference. Kept as a control arm.
    small_gap = advantages([0.4, 0.6], "grpo_std")
    big_gap = advantages([0.0, 1.0], "grpo_std")
    assert small_gap == pytest.approx(big_gap, abs=1e-6)


def test_no_spread_yields_all_zero_under_every_estimator():
    for est in ESTIMATORS:
        assert advantages([1.0, 1.0, 1.0], est) == [0.0, 0.0, 0.0]
        assert advantages([0.0, 0.0], est) == [0.0, 0.0]


def test_advantages_sum_to_zero():
    for est in ESTIMATORS:
        out = advantages([1.0, 0.0, 1.0, 0.0], est)
        assert sum(out) == pytest.approx(0.0, abs=1e-9)


def test_empty_group_returns_empty():
    assert advantages([], "drgrpo") == []


def test_unknown_estimator_is_a_loud_error_not_a_default():
    with pytest.raises(AdvantageConfigError):
        advantages([0.0, 1.0], "whatever_the_trainer_happened_to_use")


def test_legacy_alias_still_resolves_to_the_old_behaviour():
    from harness.rl_from_oracle import grpo_advantages
    assert grpo_advantages([0.0, 1.0]) == advantages([0.0, 1.0], "grpo_std")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_advantages.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'harness.advantages'`

- [ ] **Step 3: Write minimal implementation**

Create `harness/advantages.py`:

```python
"""advantages.py -- group-relative advantage estimators, selectable and named.

Dividing by the group standard deviation (the original GRPO formulation) makes a
group's gradient magnitude depend on how mixed that group happened to be: a group
split 1-7 and a group split 4-4 are rescaled to the same size even though one
carries far more information about the reward gap. Dr.GRPO drops the division and
the per-sequence length normalization, which removes both biases.

The legacy estimator stays available and named so it can serve as a control arm.
The estimator that produced a set of advantages is recorded in the receipt: a
trainer and an auditor computing different estimators would silently disagree
forever, so the name travels with the numbers.
"""
from __future__ import annotations

from statistics import fmean, pstdev

EPS = 1e-8
ESTIMATORS = frozenset({"drgrpo", "grpo_std"})


class AdvantageConfigError(ValueError):
    """An unrecognized estimator name. Never defaulted: a silent fallback here
    is a silently wrong gradient."""


def advantages(rewards: list[float], estimator: str = "drgrpo") -> list[float]:
    """Group-relative advantages. Output length always matches input length.

    A group with no spread returns all zeros under every estimator: all-pass and
    all-fail teach nothing, and we report that rather than manufacturing a
    gradient.
    """
    if estimator not in ESTIMATORS:
        raise AdvantageConfigError(
            f"unknown estimator {estimator!r}; known: {sorted(ESTIMATORS)}")
    if not rewards:
        return []
    mean = fmean(rewards)
    centred = [r - mean for r in rewards]
    if estimator == "drgrpo":
        return centred
    spread = pstdev(rewards)
    if spread <= EPS:
        return [0.0 for _ in rewards]
    return [c / (spread + EPS) for c in centred]
```

In `harness/rl_from_oracle.py`, delete the `grpo_advantages` function body (lines 47-60) and the now-unused `from statistics import fmean, pstdev` usage stays (it is still used by `collect`). Replace the deleted function with:

```python
from .advantages import advantages as _advantages


def grpo_advantages(rewards: list[float]) -> list[float]:
    """Legacy alias preserved for existing callers and tests. New code calls
    harness.advantages.advantages() with an explicit estimator."""
    return _advantages(rewards, "grpo_std")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_advantages.py tests/test_rl_from_oracle.py -v`
Expected: PASS. `test_advantages.py` 8 passed, `test_rl_from_oracle.py` unchanged and green.

- [ ] **Step 5: Commit**

```bash
git add harness/advantages.py harness/rl_from_oracle.py tests/test_advantages.py
git commit -m "feat(advantages): Dr.GRPO estimator, selectable and named"
```

---

### Task 5: One temperature per group, and a four-way-aware collect

**Files:**
- Modify: `harness/rl_from_oracle.py` (`Rollout`, `RLGroup`, `RLFromOracle.__init__`, `RLFromOracle.collect`)
- Test: `tests/test_rl_group_sampling.py`

**Interfaces:**
- Consumes: `harness.advantages.advantages`, `harness.verdict.Verdict`/`Execution`/`Attribution`/`is_dispositive` (Tasks 1 and 4)
- Produces: `RLFromOracle(proposer, group_size=8, temperature=1.0, estimator="drgrpo", max_new_tokens=None)`; `Rollout` gains `verdict: Verdict`, `attribution: Attribution`, `loss_masked: bool`; `RLGroup` gains `temperature: float`, `estimator: str`, `n_undecided: int`, `n_excluded: int`, `excluded: list[dict]`; `RLFromOracle.collect` no longer calls `budget_schedule`

**Why:** `budget_schedule(n)` returns a grid of distinct `(temperature, seed)` pairs whose first entry is `(0.0, 0)`. That grid is correct for best-of-N selection, where diversity is the point. It is wrong for a policy-gradient group, where every member must be a sample from *the same* policy: mixed temperatures make the importance ratio wrong for every member, and the greedy member pays the policy to become deterministic. Diversity in training comes from fresh seeds at one temperature.

- [ ] **Step 1: Write the failing test**

Create `tests/test_rl_group_sampling.py`:

```python
from harness.rl_from_oracle import RLFromOracle
from harness.oracle import OracleResult
from harness.task import Task
from harness.verdict import Verdict, Execution, Attribution


class _RecordingProposer:
    """Records the sampling parameters it was called with."""

    def __init__(self):
        self.calls = []

    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=None):
        self.calls.append({"seed": seed, "temperature": temperature})

        class _Out:
            text = f"candidate-{seed}"
        return _Out()


class _AlwaysOracle:
    oracle_type = "stub"

    def __init__(self, result):
        self._result = result

    def verify(self, candidate, task):
        return self._result


def _task():
    return Task(task_id="t1", prompt="p", oracle_cmd="true", max_new_tokens=8)


def _pass_fail_oracle():
    class _Alternating:
        oracle_type = "stub"

        def __init__(self):
            self.n = 0

        def verify(self, candidate, task):
            self.n += 1
            return OracleResult(passed=(self.n % 2 == 0), cmd="c",
                                output_hash="h", stdout_excerpt="", rc=0)
    return _Alternating()


def test_every_rollout_in_a_group_shares_one_temperature():
    p = _RecordingProposer()
    rl = RLFromOracle(p, group_size=4, temperature=0.9)
    rl.collect(_task(), _pass_fail_oracle())
    temps = {c["temperature"] for c in p.calls}
    assert temps == {0.9}


def test_no_greedy_sample_ever_enters_a_training_group():
    p = _RecordingProposer()
    rl = RLFromOracle(p, group_size=8, temperature=1.0)
    rl.collect(_task(), _pass_fail_oracle())
    assert all(c["temperature"] > 0.0 for c in p.calls)


def test_seeds_are_distinct_within_a_group():
    p = _RecordingProposer()
    rl = RLFromOracle(p, group_size=6, temperature=1.0)
    rl.collect(_task(), _pass_fail_oracle())
    seeds = [c["seed"] for c in p.calls]
    assert len(set(seeds)) == 6


def test_seeds_advance_between_steps_so_groups_are_not_replays():
    p = _RecordingProposer()
    rl = RLFromOracle(p, group_size=4, temperature=1.0)
    rl.collect(_task(), _pass_fail_oracle())
    first = [c["seed"] for c in p.calls]
    p.calls.clear()
    rl.collect(_task(), _pass_fail_oracle())
    second = [c["seed"] for c in p.calls]
    assert set(first).isdisjoint(second)


def test_undecided_is_loss_masked_with_zero_advantage_and_still_counted():
    undecided = OracleResult(verdict_=Verdict.UNDECIDED, cmd="c",
                             output_hash="h", stdout_excerpt="", rc=0)
    rl = RLFromOracle(_RecordingProposer(), group_size=4, temperature=1.0)
    g = rl.collect(_task(), _AlwaysOracle(undecided))
    assert g.n_undecided == 4
    assert all(r.loss_masked for r in g.rollouts)
    assert all(r.advantage == 0.0 for r in g.rollouts)
    assert g.learnable is False


def test_candidate_attributable_timeout_scores_a_real_fail():
    timed_out = OracleResult(verdict_=Verdict.FAIL, cmd="c", output_hash="h",
                             stdout_excerpt="", rc=1,
                             execution=Execution.TIMEOUT)
    rl = RLFromOracle(_RecordingProposer(), group_size=2, temperature=1.0)
    g = rl.collect(_task(), _AlwaysOracle(timed_out))
    assert all(r.reward == 0.0 for r in g.rollouts)
    assert all(not r.loss_masked for r in g.rollouts)
    assert g.n_excluded == 0


def test_harness_attributable_failure_is_excluded_and_recorded():
    broken = OracleResult(verdict_=Verdict.UNVERIFIABLE, cmd="c",
                          output_hash="h", stdout_excerpt="", rc=1,
                          execution=Execution.HARNESS_ERROR)
    rl = RLFromOracle(_RecordingProposer(), group_size=3, temperature=1.0)
    g = rl.collect(_task(), _AlwaysOracle(broken))
    assert g.n_excluded == 3
    assert len(g.excluded) == 3
    assert g.excluded[0]["attribution"] == Attribution.HARNESS.value
    assert g.rollouts == []


def test_group_records_its_temperature_and_estimator():
    rl = RLFromOracle(_RecordingProposer(), group_size=2, temperature=0.7,
                      estimator="drgrpo")
    g = rl.collect(_task(), _pass_fail_oracle())
    assert g.temperature == 0.7
    assert g.estimator == "drgrpo"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_rl_group_sampling.py -v`
Expected: FAIL. `RLFromOracle.__init__` rejects the `temperature` keyword.

- [ ] **Step 3: Write minimal implementation**

In `harness/rl_from_oracle.py`:

Add to imports:

```python
from .verdict import Verdict, Attribution, is_dispositive
from .advantages import advantages as _advantages, ESTIMATORS
```

Add three fields to `Rollout` (after `text_hash: str = ""`):

```python
    verdict: str = "PASS"
    attribution: str = "CANDIDATE"
    loss_masked: bool = False
```

Add five fields to `RLGroup` (after `signal_hash: str`):

```python
    temperature: float = 1.0
    estimator: str = "drgrpo"
    n_undecided: int = 0
    n_excluded: int = 0
    excluded: list[dict] = field(default_factory=list)
```

Replace `RLFromOracle.__init__` (currently lines 179-187) with:

```python
    def __init__(self, proposer: Proposer, *, group_size: int = 8,
                 temperature: float = 1.0, estimator: str = "drgrpo",
                 max_new_tokens: int | None = None, seed_origin: int = 0):
        if group_size < 2:
            raise ValueError("GRPO needs a group of at least 2 to have relative signal")
        if temperature <= 0.0:
            raise ValueError(
                "training groups need temperature > 0: a greedy sample is not a "
                "draw from the policy being optimized")
        if estimator not in ESTIMATORS:
            raise ValueError(f"unknown estimator {estimator!r}")
        self.proposer = proposer
        self.group_size = group_size
        self.temperature = temperature
        self.estimator = estimator
        self.max_new_tokens = max_new_tokens
        self._next_seed = seed_origin
```

Replace `RLFromOracle.collect` (currently lines 189-223) with:

```python
    def collect(self, task: Task, oracle: Oracle, *,
                held_out: Oracle | None = None) -> RLGroup:
        """One group: group_size samples at ONE temperature with fresh seeds.

        The multi-temperature grid used by best-of-N selection is deliberately
        not used here. Every member of a policy-gradient group must be a draw
        from the same policy, or the importance ratio is wrong for all of them.
        """
        seeds = list(range(self._next_seed, self._next_seed + self.group_size))
        self._next_seed += self.group_size
        max_tokens = self.max_new_tokens or task.max_new_tokens
        rollouts: list[Rollout] = []
        excluded: list[dict] = []

        for seed in seeds:
            out = self.proposer.generate(task.prompt, seed=seed,
                                         temperature=self.temperature,
                                         max_new_tokens=max_tokens,
                                         system=task.system)
            text = getattr(out, "text", "")
            res = oracle.verify(text, task)
            verdict = Verdict(res.verdict())
            attribution = Attribution(res.attribution)

            if not is_dispositive(verdict) and attribution is not Attribution.CANDIDATE:
                # Our bug or our missing toolchain. Dropped from the gradient and
                # written down, never scored against the candidate.
                excluded.append({"seed": seed, "verdict": verdict.value,
                                 "attribution": attribution.value,
                                 "text_hash": prompt_hash(text)})
                continue

            loss_masked = not is_dispositive(verdict)
            reward = 1.0 if verdict is Verdict.PASS else 0.0
            held_reward: float | None = None
            hacked = False
            if held_out is not None and not loss_masked:
                held_res = held_out.verify(text, task)
                held_verdict = Verdict(held_res.verdict())
                held_reward = 1.0 if held_verdict is Verdict.PASS else 0.0
                hacked = reward >= 1.0 and held_reward < 1.0
            rollouts.append(Rollout(
                text=text, seed=seed, temperature=self.temperature, reward=reward,
                held_out_reward=held_reward, reward_hacked=hacked,
                text_hash=prompt_hash(text), verdict=verdict.value,
                attribution=attribution.value, loss_masked=loss_masked))

        scored = [r for r in rollouts if not r.loss_masked]
        advs = _advantages([r.reward for r in scored], self.estimator)
        for r, a in zip(scored, advs):
            r.advantage = a

        rewards = [r.reward for r in scored]
        mean = fmean(rewards) if rewards else 0.0
        std = pstdev(rewards) if len(rewards) > 1 else 0.0
        source = getattr(oracle, "oracle_type", type(oracle).__name__)
        return RLGroup(
            task_id=task.task_id, prompt_hash=prompt_hash(task.prompt),
            reward_source=f"oracle:{source}", rollouts=rollouts,
            group_mean=mean, group_std=std,
            n_pass=sum(1 for x in rewards if x >= 1.0),
            learnable=std > EPS,
            reward_hacks=sum(1 for r in rollouts if r.reward_hacked),
            signal_hash=_hash_group(task, rollouts),
            temperature=self.temperature, estimator=self.estimator,
            n_undecided=sum(1 for r in rollouts if r.loss_masked),
            n_excluded=len(excluded), excluded=excluded)
```

Add the new fields to `RLGroup.to_dict` so they reach the receipt, inside the returned dict after `"signal_hash": self.signal_hash,`:

```python
            "temperature": self.temperature,
            "estimator": self.estimator,
            "n_undecided": self.n_undecided,
            "n_excluded": self.n_excluded,
            "excluded": self.excluded,
```

and add `"verdict": r.verdict, "attribution": r.attribution, "loss_masked": r.loss_masked,` to the per-rollout dict in the same method.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_rl_group_sampling.py tests/test_rl_from_oracle.py -v`
Expected: PASS. New file 8 passed. If an existing `test_rl_from_oracle.py` test constructed `RLFromOracle` positionally or asserted the old multi-temperature behaviour, update that test to pass `temperature=1.0` explicitly and assert one temperature; record the change in the commit message.

- [ ] **Step 5: Commit**

```bash
git add harness/rl_from_oracle.py tests/test_rl_group_sampling.py
git commit -m "fix(rl): one temperature per group, four-way verdicts, exclusion ledger"
```

---

### Task 6: Bind the verdict into the receipt hash

**Files:**
- Modify: `harness/envelope.py:47-51` (`_content_preimage`)
- Test: `tests/test_envelope_verdict_binding.py`

**Interfaces:**
- Consumes: nothing new
- Produces: `ProofEnvelope.content_hash()` and `content_sha256()` change value when `verdict` changes; `ProofEnvelope.SCHEMA_VERSION = "flywheel.envelope/v2"`

**Why:** `_content_preimage` currently pops `verdict`, `oracle_output_hash`, and `oracle_stdout_excerpt` before hashing. Flipping a stored FAIL to PASS therefore breaks no hash and no chain link. The excerpt is genuinely volatile and stays out; the verdict and the oracle output hash are the claim itself and must be inside.

**Migration note:** this changes every envelope hash. Envelopes written before this task verify under the v1 preimage. The implementation keeps `_content_preimage_v1` and tries it as a fallback so historical envelopes still re-witness, with `schema_version` recording which rule applies.

- [ ] **Step 1: Write the failing test**

Create `tests/test_envelope_verdict_binding.py`:

```python
import dataclasses

from harness.envelope import ProofEnvelope


def _env(verdict="PASS", out_hash="abc"):
    return ProofEnvelope(
        task_id="t1", candidate="def f(): pass", oracle="pytest",
        oracle_cmd="pytest -q", oracle_output_hash=out_hash, verdict=verdict,
        model_ref="m", seed=1, prompt_hash="p", budget_spent={})


def test_flipping_the_verdict_changes_the_content_hash():
    a = _env(verdict="FAIL")
    b = dataclasses.replace(a, verdict="PASS")
    assert a.content_hash() != b.content_hash()
    assert a.content_sha256() != b.content_sha256()


def test_changing_the_oracle_output_hash_changes_the_content_hash():
    a = _env(out_hash="abc")
    b = dataclasses.replace(a, oracle_output_hash="def")
    assert a.content_hash() != b.content_hash()


def test_the_volatile_excerpt_still_does_not_affect_the_hash():
    a = _env()
    b = dataclasses.replace(a, oracle_stdout_excerpt="1 passed in 0.31s")
    assert a.content_hash() == b.content_hash()


def test_identical_envelopes_still_hash_identically():
    assert _env().content_hash() == _env().content_hash()


def test_v1_preimage_is_retained_for_historical_envelopes():
    e = _env()
    assert e.content_hash_v1() != e.content_hash()
    assert len(e.content_hash_v1()) == 16
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_envelope_verdict_binding.py -v`
Expected: FAIL. `test_flipping_the_verdict_changes_the_content_hash` fails because the verdict is popped from the preimage; `content_hash_v1` does not exist.

- [ ] **Step 3: Write minimal implementation**

In `harness/envelope.py`, replace `_content_preimage` (lines 47-51) with:

```python
    SCHEMA_VERSION = "flywheel.envelope/v2"

    def _content_preimage(self) -> str:
        """v2: the verdict and the oracle output hash are INSIDE the preimage.

        They are the claim. Leaving them out meant a stored FAIL could be edited
        to PASS without breaking a single hash or chain link. Only the genuinely
        volatile excerpt (pytest's timing line) stays out.
        """
        d = asdict(self)
        d.pop("oracle_stdout_excerpt", None)
        return json.dumps(d, sort_keys=True)

    def _content_preimage_v1(self) -> str:
        """The pre-v2 rule, retained so envelopes written before the fix still
        re-witness instead of reading as tampered."""
        d = asdict(self)
        for k in ("oracle_output_hash", "verdict", "oracle_stdout_excerpt"):
            d.pop(k, None)
        return json.dumps(d, sort_keys=True)

    def content_hash_v1(self) -> str:
        return hashlib.sha256(self._content_preimage_v1().encode()).hexdigest()[:16]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_envelope_verdict_binding.py -v`
Expected: PASS, 5 passed

- [ ] **Step 5: Run the envelope and chain slice**

Run: `python -m pytest tests/test_envelope.py tests/test_chain.py tests/test_witness.py tests/test_transitive_witness.py tests/test_grounding_closure.py -q`
Expected: PASS. Any test asserting a hard-coded historical hash should call `content_hash_v1()` instead; note each such change in the commit message.

- [ ] **Step 6: Commit**

```bash
git add harness/envelope.py tests/test_envelope_verdict_binding.py
git commit -m "fix(envelope): bind verdict and oracle output hash into the content preimage"
```

---

### Task 7: Gateway authentication

**Files:**
- Create: `harness/gateway_auth.py`
- Modify: `harness/gateway.py` (imports, `_Handler.do_GET` at :1008, `_Handler.do_POST` at :1014, `main` at :2355)
- Test: `tests/test_gateway_auth.py`

**Interfaces:**
- Consumes: nothing new
- Produces: `load_or_create_token(home: Path) -> str`; `check(headers: Mapping, method: str, token: str, *, allowed_hosts: frozenset[str]) -> tuple[bool, str]` returning `(ok, reason)`; `TOKEN_FILENAME = "gateway.token"`; `DEFAULT_HOSTS = frozenset({"127.0.0.1", "localhost", "[::1]"})`

**Why:** the gateway binds localhost with no authentication while exposing routes that write OS keychain entries, register MCP servers by argv, install packages, and run an edit-and-execute agent loop. Any local process reaches all of it, and a `Host` header is never validated, so DNS rebinding turns a visited web page into a caller. Phase 0 adds a bearer token, a Host allowlist, and a `Content-Type: application/json` requirement on state-changing methods (which defeats CORS-simple cross-origin POSTs).

- [ ] **Step 1: Write the failing test**

Create `tests/test_gateway_auth.py`:

```python
import os
import stat

import pytest

from harness.gateway_auth import (
    load_or_create_token, check, TOKEN_FILENAME, DEFAULT_HOSTS,
)

TOK = "t" * 43


def _h(**kw):
    return {k.replace("_", "-"): v for k, v in kw.items()}


def test_token_is_created_once_and_reused(tmp_path):
    a = load_or_create_token(tmp_path)
    b = load_or_create_token(tmp_path)
    assert a == b
    assert len(a) >= 32
    assert (tmp_path / TOKEN_FILENAME).exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_token_file_is_not_world_readable(tmp_path):
    load_or_create_token(tmp_path)
    mode = (tmp_path / TOKEN_FILENAME).stat().st_mode
    assert not (mode & stat.S_IRGRP)
    assert not (mode & stat.S_IROTH)


def test_correct_bearer_token_on_a_local_host_passes():
    ok, _ = check(_h(Authorization=f"Bearer {TOK}", Host="127.0.0.1:8799",
                     Content_Type="application/json"),
                  "POST", TOK, allowed_hosts=DEFAULT_HOSTS)
    assert ok is True


def test_missing_token_is_refused():
    ok, reason = check(_h(Host="127.0.0.1:8799"), "GET", TOK,
                       allowed_hosts=DEFAULT_HOSTS)
    assert ok is False
    assert reason == "no_token"


def test_wrong_token_is_refused():
    ok, reason = check(_h(Authorization="Bearer wrong", Host="127.0.0.1:8799"),
                       "GET", TOK, allowed_hosts=DEFAULT_HOSTS)
    assert ok is False
    assert reason == "bad_token"


def test_foreign_host_header_is_refused_even_with_a_valid_token():
    # DNS rebinding: the browser resolves attacker.example to 127.0.0.1 and
    # sends its own Host. The token would not be known, but the Host check is
    # the layer that does not depend on that assumption.
    ok, reason = check(_h(Authorization=f"Bearer {TOK}", Host="attacker.example"),
                       "GET", TOK, allowed_hosts=DEFAULT_HOSTS)
    assert ok is False
    assert reason == "bad_host"


def test_state_changing_request_requires_a_json_content_type():
    ok, reason = check(_h(Authorization=f"Bearer {TOK}", Host="localhost:8799",
                          Content_Type="text/plain"),
                       "POST", TOK, allowed_hosts=DEFAULT_HOSTS)
    assert ok is False
    assert reason == "bad_content_type"


def test_get_does_not_require_a_content_type():
    ok, _ = check(_h(Authorization=f"Bearer {TOK}", Host="localhost:8799"),
                  "GET", TOK, allowed_hosts=DEFAULT_HOSTS)
    assert ok is True


def test_token_comparison_does_not_short_circuit():
    import inspect
    from harness import gateway_auth
    assert "compare_digest" in inspect.getsource(gateway_auth.check)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_gateway_auth.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'harness.gateway_auth'`

- [ ] **Step 3: Write minimal implementation**

Create `harness/gateway_auth.py`:

```python
"""gateway_auth.py -- the gateway is not public, and localhost is not a wall.

The gateway exposes routes that write keychain entries, register MCP servers by
argv, install packages, and run an edit-and-execute agent loop. Binding
127.0.0.1 stops remote hosts and nothing else: every local process reaches it,
and a browser that resolves a name to 127.0.0.1 reaches it too unless the Host
header is checked.

Three layers, all cheap: a bearer token the caller must know, a Host allowlist
that defeats DNS rebinding, and a JSON content-type requirement on
state-changing methods that defeats the CORS-simple cross-origin POST.
"""
from __future__ import annotations

import os
import secrets
from hmac import compare_digest
from pathlib import Path
from typing import Mapping

TOKEN_FILENAME = "gateway.token"
DEFAULT_HOSTS = frozenset({"127.0.0.1", "localhost", "[::1]"})
STATE_CHANGING = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def load_or_create_token(home: Path) -> str:
    """Read the gateway token, minting one on first use. Owner-readable only."""
    home = Path(home)
    home.mkdir(parents=True, exist_ok=True)
    path = home / TOKEN_FILENAME
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    token = secrets.token_urlsafe(32)
    path.write_text(token, encoding="utf-8")
    if os.name != "nt":
        path.chmod(0o600)
    return token


def _host_of(headers: Mapping) -> str:
    raw = headers.get("Host", "") or ""
    if raw.startswith("["):                     # bracketed IPv6 literal
        return raw.split("]", 1)[0] + "]"
    return raw.split(":", 1)[0]


def check(headers: Mapping, method: str, token: str, *,
          allowed_hosts: frozenset[str] = DEFAULT_HOSTS) -> tuple[bool, str]:
    """Return (ok, reason). Reason is a stable code, never a secret."""
    if _host_of(headers) not in allowed_hosts:
        return False, "bad_host"
    auth = headers.get("Authorization", "") or ""
    if not auth.startswith("Bearer "):
        return False, "no_token"
    if not compare_digest(auth[7:], token):
        return False, "bad_token"
    if method.upper() in STATE_CHANGING:
        ctype = (headers.get("Content-Type", "") or "").split(";", 1)[0].strip()
        if ctype != "application/json":
            return False, "bad_content_type"
    return True, "ok"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_gateway_auth.py -v`
Expected: PASS, 9 passed (8 on Windows, where the permission test skips)

- [ ] **Step 5: Wire it into the gateway**

In `harness/gateway.py`, add to the imports near the top:

```python
from harness.gateway_auth import load_or_create_token, check as _auth_check, DEFAULT_HOSTS
```

Add a class attribute to `_Handler` (next to `cors = False` at :773):

```python
    auth_token = ""                           # set by main(); "" disables the check
    allowed_hosts = DEFAULT_HOSTS
```

Add this method to `_Handler`:

```python
    def _authorized(self) -> bool:
        """Refuse before dispatch. Returns True when the request may proceed."""
        if not self.auth_token:
            return True
        ok, reason = _auth_check(self.headers, self.command, self.auth_token,
                                 allowed_hosts=self.allowed_hosts)
        if ok:
            return True
        body = json.dumps({"error": "unauthorized", "reason": reason}).encode()
        self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return False
```

Change `do_GET` (:1008) and `do_POST` (:1014) to gate on it:

```python
    def do_GET(self):
        if not self._authorized():
            return
        try:
            self._get()
        except Exception as e:
            self._safe_500(e)

    def do_POST(self):
        if not self._authorized():
            return
        try:
            self._post()
        except Exception as e:
            self._safe_500(e)
```

In `main` (:2355), before `httpd = ThreadingHTTPServer(...)` at :2370, add:

```python
    flywheel_home = Path(os.environ.get("FLYWHEEL_HOME", str(Path.home() / ".flywheel")))
    _Handler.auth_token = load_or_create_token(flywheel_home)
    print(f"gateway token: {flywheel_home / 'gateway.token'}")
```

- [ ] **Step 6: Verify the gateway still serves and now refuses**

Run:

```bash
python -m pytest tests/test_gateway.py -q
```

Expected: PASS. Existing gateway tests construct `_Handler` without setting `auth_token`, so the check is disabled for them by the `if not self.auth_token` guard.

Then a live check in one shell:

```bash
FLYWHEEL_HOME=/tmp/fwtest python -m harness.gateway --port 8799
```

and in another:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8799/api/lanes
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $(cat /tmp/fwtest/gateway.token)" http://127.0.0.1:8799/api/lanes
```

Expected: `401` then `200`.

- [ ] **Step 7: Commit**

```bash
git add harness/gateway_auth.py harness/gateway.py tests/test_gateway_auth.py
git commit -m "feat(gateway): bearer token, Host allowlist, JSON content-type gate"
```

---

### Task 8: The disproof gate, end to end, behind one command

**Files:**
- Create: `harness/gate.py`
- Modify: `harness/cli_entry.py` (`_dispatch_umbrella` at :149)
- Test: `tests/test_gate_end_to_end.py`

**Interfaces:**
- Consumes: `harness.matmul_oracle.MatMulSchemeOracle`/`strassen_scheme`/`perturb_scheme`/`dumps`, `harness.rl_from_oracle.RLFromOracle`, `harness.envelope.ProofEnvelope`, `harness.verdict.Verdict` (Tasks 1, 2, 5, 6)
- Produces: `run_gate(out_dir: Path) -> GateReport`; `GateReport` dataclass with `verdict: str`, `group_signal_hash: str`, `envelope_hash: str`, `rewitness: str`, `steps: list[dict]`; CLI verb `flywheel gate`

**Why this is the gate:** it proves the whole chain moves with code that already exists, using an oracle that never executes candidate code. Nothing is stubbed. If this command cannot be made to print MATCH within Phase 0's week, CC-1's premise is disproven at the cost of one week.

The scheme proposer is deterministic and local: seed 0 returns a correct Strassen scheme, other seeds return perturbed ones. There is no model in this task, by design. The chain under test is oracle plus group plus receipt plus re-witness, not generation.

- [ ] **Step 1: Write the failing test**

Create `tests/test_gate_end_to_end.py`:

```python
from harness.gate import run_gate


def test_gate_reaches_match(tmp_path):
    r = run_gate(tmp_path)
    assert r.verdict == "PASS"
    assert r.rewitness == "MATCH"


def test_gate_group_is_learnable_because_the_scheme_pool_is_mixed(tmp_path):
    r = run_gate(tmp_path)
    steps = {s["step"]: s for s in r.steps}
    assert steps["collect"]["n_pass"] >= 1
    assert steps["collect"]["n_pass"] < steps["collect"]["group_size"]
    assert steps["collect"]["learnable"] is True


def test_gate_group_used_one_temperature(tmp_path):
    r = run_gate(tmp_path)
    steps = {s["step"]: s for s in r.steps}
    assert steps["collect"]["temperature"] > 0.0
    assert steps["collect"]["estimator"] == "drgrpo"


def test_gate_writes_an_envelope_that_rewitnesses(tmp_path):
    r = run_gate(tmp_path)
    assert (tmp_path / "gate_envelope.json").exists()
    assert len(r.envelope_hash) == 16


def test_a_tampered_envelope_fails_to_rewitness(tmp_path):
    import json
    run_gate(tmp_path)
    p = tmp_path / "gate_envelope.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["verdict"] = "PASS" if d["verdict"] == "FAIL" else "FAIL"
    p.write_text(json.dumps(d, indent=2, sort_keys=True), encoding="utf-8")

    from harness.gate import rewitness_envelope
    assert rewitness_envelope(p) == "DRIFT"


def test_gate_is_deterministic(tmp_path):
    a = run_gate(tmp_path / "a")
    b = run_gate(tmp_path / "b")
    assert a.group_signal_hash == b.group_signal_hash
    assert a.envelope_hash == b.envelope_hash
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_gate_end_to_end.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'harness.gate'`

- [ ] **Step 3: Write minimal implementation**

Create `harness/gate.py`:

```python
"""gate.py -- the Phase 0 disproof gate.

One command that takes the existing chain end to end: an exact symbolic oracle
disposes a group of candidate matmul schemes, the group is scored with the named
estimator, the accepted candidate is sealed into a proof envelope, and the
envelope is re-witnessed by re-running the same oracle over the stored candidate.

Everything here already existed in the repository and was never wired together.
If this command cannot reach MATCH, the premise that these parts compose is
false, and we learn it in week one.

There is no model in this gate on purpose. The proposer is a deterministic local
function, so what is under test is the oracle plus group plus receipt plus
re-witness chain, not generation.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .envelope import ProofEnvelope
from .matmul_oracle import (
    MatMulSchemeOracle, strassen_scheme, perturb_scheme, dumps,
)
from .rl_from_oracle import RLFromOracle
from .task import Task
from .verdict import Verdict

GROUP_SIZE = 4
TEMPERATURE = 1.0
ESTIMATOR = "drgrpo"


@dataclass
class GateReport:
    verdict: str
    group_signal_hash: str
    envelope_hash: str
    rewitness: str
    steps: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"verdict": self.verdict, "group_signal_hash": self.group_signal_hash,
                "envelope_hash": self.envelope_hash, "rewitness": self.rewitness,
                "steps": self.steps}


class _SchemeProposer:
    """Deterministic stand-in for a policy: seed 0 yields the correct Strassen
    scheme, every other seed yields a perturbed one. The pool is deliberately
    mixed so the group carries a gradient and the gate exercises the learnable
    path rather than the degenerate all-fail one."""

    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=None):
        scheme = (strassen_scheme() if seed % GROUP_SIZE == 0
                  else perturb_scheme(strassen_scheme(), triple=seed % 7,
                                      field="w", pos=seed % 4))

        class _Out:
            text = dumps(scheme)
        return _Out()


def _task() -> Task:
    return Task(task_id="gate-matmul-2x2x2",
                prompt="Emit a rank-7 bilinear scheme for 2x2x2 matmul.",
                oracle_cmd="matmul_identity", max_new_tokens=4096)


def rewitness_envelope(path: Path) -> str:
    """Re-run the oracle over the stored candidate and compare to the sealed
    record. MATCH, DRIFT, or UNVERIFIABLE. Never assumes MATCH."""
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return "UNVERIFIABLE"
    candidate = d.get("candidate")
    if candidate is None:
        return "UNVERIFIABLE"
    res = MatMulSchemeOracle().verify(candidate, None)
    if res.verdict() != d.get("verdict"):
        return "DRIFT"
    if res.output_hash != d.get("oracle_output_hash"):
        return "DRIFT"
    return "MATCH"


def run_gate(out_dir: Path) -> GateReport:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    steps: list[dict] = []

    oracle = MatMulSchemeOracle()
    task = _task()

    rl = RLFromOracle(_SchemeProposer(), group_size=GROUP_SIZE,
                      temperature=TEMPERATURE, estimator=ESTIMATOR)
    group = rl.collect(task, oracle)
    steps.append({"step": "collect", "group_size": GROUP_SIZE,
                  "temperature": group.temperature, "estimator": group.estimator,
                  "n_pass": group.n_pass, "learnable": group.learnable,
                  "n_undecided": group.n_undecided, "n_excluded": group.n_excluded,
                  "signal_hash": group.signal_hash})

    winner = next((r for r in group.rollouts if r.reward >= 1.0), None)
    if winner is None:
        report = GateReport(verdict=Verdict.UNVERIFIABLE.value,
                            group_signal_hash=group.signal_hash,
                            envelope_hash="", rewitness="UNVERIFIABLE", steps=steps)
        (out_dir / "gate_report.json").write_text(
            json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        return report

    res = oracle.verify(winner.text, task)
    steps.append({"step": "verify", "verdict": res.verdict(),
                  "output_hash": res.output_hash,
                  "attribution": res.attribution.value})

    env = ProofEnvelope(
        task_id=task.task_id, candidate=winner.text, oracle=oracle.oracle_type,
        oracle_cmd="matmul_identity", oracle_output_hash=res.output_hash,
        verdict=res.verdict(), model_ref="gate:deterministic-scheme-proposer",
        seed=winner.seed, prompt_hash=group.prompt_hash,
        budget_spent={"oracle_calls": GROUP_SIZE + 1},
        oracle_stdout_excerpt=res.stdout_excerpt)
    env_path = out_dir / "gate_envelope.json"
    env_path.write_text(env.to_json(), encoding="utf-8")
    steps.append({"step": "seal", "envelope_hash": env.content_hash(),
                  "path": str(env_path)})

    verdict_of_rewitness = rewitness_envelope(env_path)
    steps.append({"step": "rewitness", "result": verdict_of_rewitness})

    report = GateReport(verdict=res.verdict(), group_signal_hash=group.signal_hash,
                        envelope_hash=env.content_hash(),
                        rewitness=verdict_of_rewitness, steps=steps)
    (out_dir / "gate_report.json").write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return report
```

In `harness/cli_entry.py`, inside `_dispatch_umbrella` (:149), add a branch before the existing dispatch fallthrough:

```python
    if command == "gate":
        from pathlib import Path
        from harness.gate import run_gate
        out = Path(argv[0]) if argv else (find_repo_root() / "artifacts" / "gate")
        report = run_gate(out)
        for s in report.steps:
            print(f"  {s['step']}: " + ", ".join(
                f"{k}={v}" for k, v in s.items() if k != "step"))
        print(f"verdict={report.verdict} rewitness={report.rewitness}")
        print(f"envelope={report.envelope_hash} signal={report.group_signal_hash}")
        return 0 if report.rewitness == "MATCH" else 1
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_gate_end_to_end.py -v`
Expected: PASS, 6 passed

- [ ] **Step 5: Run the command itself**

Run: `python -m harness.cli_entry gate`
Expected output ends with:

```
verdict=PASS rewitness=MATCH
```

and exit status 0. Confirm with `echo $?` (bash) or `$LASTEXITCODE` (PowerShell).

- [ ] **Step 6: Commit**

```bash
git add harness/gate.py harness/cli_entry.py tests/test_gate_end_to_end.py
git commit -m "feat(gate): Phase 0 disproof gate, oracle to receipt to re-witness"
```

---

### Task 9: CI, the mechanical stranger

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `scripts/check_file_gate.py`
- Create: `project-docs/records/2026-07-25-file-gate-burndown.md`
- Test: `tests/test_file_gate.py`

**Interfaces:**
- Consumes: nothing from earlier tasks
- Produces: `scripts/check_file_gate.py` exposing `over_gate(root: Path, limit: int = 300) -> list[tuple[str, int]]` and `load_grandfathered(path: Path) -> dict[str, int]`; exit 1 when a new file exceeds the gate or a grandfathered file grows

**Why:** the 300-line gate and the stdlib-only rule are both currently honor-system, and the panel found 16 existing violations. Freezing the violations on a burn-down list makes the rule enforceable today without a refactor, and blocks the list from growing.

- [ ] **Step 1: Write the failing test**

Create `tests/test_file_gate.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from check_file_gate import over_gate, load_grandfathered  # noqa: E402


def test_over_gate_finds_a_long_file(tmp_path):
    (tmp_path / "long.py").write_text("x = 1\n" * 400, encoding="utf-8")
    (tmp_path / "short.py").write_text("x = 1\n", encoding="utf-8")
    found = dict(over_gate(tmp_path, limit=300))
    assert "long.py" in found
    assert found["long.py"] == 400
    assert "short.py" not in found


def test_grandfather_list_parses(tmp_path):
    p = tmp_path / "burndown.md"
    p.write_text(
        "# burn-down\n\n"
        "| file | lines |\n"
        "|---|---|\n"
        "| harness/gateway.py | 2391 |\n"
        "| harness/serve.py | 420 |\n",
        encoding="utf-8")
    g = load_grandfathered(p)
    assert g["harness/gateway.py"] == 2391
    assert g["harness/serve.py"] == 420


def test_the_real_repo_has_a_burndown_covering_every_current_violation():
    root = Path(__file__).resolve().parent.parent
    listed = load_grandfathered(
        root / "project-docs" / "records" / "2026-07-25-file-gate-burndown.md")
    actual = dict(over_gate(root / "harness", limit=300))
    unlisted = [f for f in actual if f"harness/{f}" not in listed]
    assert unlisted == [], f"unlisted violations: {unlisted}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_file_gate.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'check_file_gate'`

- [ ] **Step 3: Write minimal implementation**

Create `scripts/check_file_gate.py`:

```python
"""check_file_gate.py -- enforce the 300-line file gate without a refactor.

Existing violations are frozen on a burn-down list with their line counts. A new
file over the gate fails CI; a grandfathered file that GROWS fails CI. The list
can only shrink.
"""
from __future__ import annotations

import sys
from pathlib import Path

LIMIT = 300


def over_gate(root: Path, limit: int = LIMIT) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    root = Path(root)
    for p in sorted(root.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        n = sum(1 for _ in p.open("r", encoding="utf-8", errors="replace"))
        if n > limit:
            out.append((p.relative_to(root).as_posix(), n))
    return out


def load_grandfathered(path: Path) -> dict[str, int]:
    """Parse the burn-down markdown table into {path: max_allowed_lines}."""
    g: dict[str, int] = {}
    p = Path(path)
    if not p.exists():
        return g
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| ") or line.startswith("| file") or "---" in line:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) >= 2 and cells[1].isdigit():
            g[cells[0]] = int(cells[1])
    return g


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    listed = load_grandfathered(
        root / "project-docs" / "records" / "2026-07-25-file-gate-burndown.md")
    failures: list[str] = []
    for rel, n in over_gate(root / "harness"):
        key = f"harness/{rel}"
        if key not in listed:
            failures.append(f"NEW violation: {key} is {n} lines (limit {LIMIT})")
        elif n > listed[key]:
            failures.append(f"GREW: {key} is {n} lines, frozen at {listed[key]}")
    for f in failures:
        print(f)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
```

Generate the burn-down list by running:

```bash
python -c "
import sys; sys.path.insert(0, 'scripts')
from pathlib import Path
from check_file_gate import over_gate
rows = over_gate(Path('harness'))
print('# File gate burn-down (frozen 2026-07-25)')
print()
print('The 300-line gate applies to every file in harness/. These violations')
print('predate enforcement and are frozen at their current size. A file on this')
print('list may shrink and leave; it may never grow. New files may not join.')
print()
print('| file | lines |')
print('|---|---|')
for rel, n in rows:
    print(f'| harness/{rel} | {n} |')
" > project-docs/records/2026-07-25-file-gate-burndown.md
```

Create `.github/workflows/ci.yml`:

```yaml
name: ci

on:
  push:
    branches: ["**"]
  pull_request:

jobs:
  test:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
        python: ["3.10", "3.13"]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python }}
      - name: Install test tooling only
        run: python -m pip install pytest pytest-timeout
      - name: Phase 0 slice
        run: >
          python -m pytest
          tests/test_verdict.py
          tests/test_oracle_verdict_widening.py
          tests/test_oracle_env_boundary.py
          tests/test_advantages.py
          tests/test_rl_group_sampling.py
          tests/test_envelope_verdict_binding.py
          tests/test_gateway_auth.py
          tests/test_gate_end_to_end.py
          tests/test_file_gate.py
          -q

  gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - name: The disproof gate runs with no dependencies at all
        run: python -m harness.cli_entry gate

  stdlib_only:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - name: The verifier path imports nothing outside the stdlib
        run: |
          python - <<'PY'
          import ast, sys
          from pathlib import Path
          THIRD_PARTY = {"torch", "transformers", "peft", "trl", "numpy",
                         "requests", "httpx", "pydantic", "vllm", "unsloth"}
          bad = []
          for p in Path("harness").rglob("*.py"):
              tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
              for node in ast.walk(tree):
                  mods = []
                  if isinstance(node, ast.Import):
                      mods = [a.name.split(".")[0] for a in node.names]
                  elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                      mods = [node.module.split(".")[0]]
                  for m in mods:
                      if m in THIRD_PARTY:
                          bad.append(f"{p}:{node.lineno} imports {m}")
          print("\n".join(bad) or "clean")
          sys.exit(1 if bad else 0)
          PY

  file_gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - run: python scripts/check_file_gate.py
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_file_gate.py -v`
Expected: PASS, 3 passed

- [ ] **Step 5: Run the gate script and the stdlib check locally**

Run: `python scripts/check_file_gate.py`
Expected: no output, exit 0. If it prints a NEW violation, the file was created by an earlier task and must be split before this task can complete.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/ci.yml scripts/check_file_gate.py \
  project-docs/records/2026-07-25-file-gate-burndown.md tests/test_file_gate.py
git commit -m "ci: three-OS matrix, stdlib-only assertion, file gate burn-down"
```

---

### Task 10: Phase 0 acceptance and the honest report

**Files:**
- Create: `project-docs/records/2026-07-25-phase0-acceptance.md`
- Modify: `STATE.md` (prepend a session entry)

**Interfaces:**
- Consumes: every prior task
- Produces: the written record that decides whether Phase 1 begins

- [ ] **Step 1: Run the full Phase 0 slice**

Run:

```bash
python -m pytest tests/test_verdict.py tests/test_oracle_verdict_widening.py tests/test_oracle_env_boundary.py tests/test_advantages.py tests/test_rl_group_sampling.py tests/test_envelope_verdict_binding.py tests/test_gateway_auth.py tests/test_gate_end_to_end.py tests/test_file_gate.py -v
```

Expected: all pass. Record the exact count.

- [ ] **Step 2: Run the reverse-import regression surface**

Run:

```bash
python -m pytest tests/test_oracle.py tests/test_loop.py tests/test_selector.py tests/test_search.py tests/test_escalation.py tests/test_consensus.py tests/test_calibration.py tests/test_matmul_oracle.py tests/test_rl_from_oracle.py tests/test_envelope.py tests/test_chain.py tests/test_witness.py tests/test_transitive_witness.py tests/test_grounding_closure.py tests/test_gateway.py -q
```

Expected: pass. Any failure is a Phase 0 regression and must be fixed before the report is written, not documented around.

- [ ] **Step 3: Run the gate one final time from a clean clone**

Run:

```bash
git clone --depth 1 file://$(pwd) /tmp/fw-clean && cd /tmp/fw-clean && python -m harness.cli_entry gate
```

Expected: `verdict=PASS rewitness=MATCH`, exit 0, with no `pip install` of anything.

- [ ] **Step 4: Write the acceptance record**

Create `project-docs/records/2026-07-25-phase0-acceptance.md` containing, with real numbers and no rounding in your favour:

- The Phase 0 slice result (tests passed, tests failed, exact command).
- The regression surface result.
- The clean-clone gate transcript, pasted verbatim.
- Which of the five panel-identified live defects are now closed, each with the test that would fail if it regressed: multi-temperature groups (`tests/test_rl_group_sampling.py::test_every_rollout_in_a_group_shares_one_temperature`), UNVERIFIABLE unrepresentable (`tests/test_oracle_verdict_widening.py::test_passed_raises_on_a_non_dispositive_verdict`), verdict outside the hash (`tests/test_envelope_verdict_binding.py::test_flipping_the_verdict_changes_the_content_hash`), environment inheritance into candidate execution (`tests/test_oracle_env_boundary.py::test_a_secret_in_the_parent_environment_does_not_reach_the_child`), unauthenticated gateway (`tests/test_gateway_auth.py::test_foreign_host_header_is_refused_even_with_a_valid_token`).
- **What Phase 0 does NOT prove**, stated plainly: no model was trained, no weight moved, no uplift was measured, the receipt is not yet signed, the ledger has no inclusion or consistency proofs, no stranger has re-derived anything, and the gate's proposer is a deterministic local function rather than a policy. Phase 0 proves the parts compose, and nothing more.
- The verdict on the gate: PASS means Phase 1 begins; anything else means the premise is disproven and the program stops for a decision.

- [ ] **Step 5: Update STATE.md**

Prepend a dated entry under the existing header, in the file's established style, recording what shipped, the test counts, and the honest non-claims from step 4.

- [ ] **Step 6: Commit**

```bash
git add project-docs/records/2026-07-25-phase0-acceptance.md STATE.md
git commit -m "docs: Phase 0 acceptance record and honest non-claims"
```

---

### Task 11: The two invariants that are cheap now and expensive later

**Files:**
- Create: `tests/test_accept_path_purity.py`
- Create: `tests/test_no_aggregate_over_the_person.py`

**Interfaces:**
- Consumes: `harness.gate.run_gate` (Task 8)
- Produces: no production code; two permanent invariant tests

**Source:** `project-docs/records/2026-07-25-expert-grounding-requirements.md` sections 0.2 and PC-1. Both are schema-shaped: cheap to assert before receipts accumulate, expensive to retrofit afterwards.

**0.2, stated positively:** a verdict is a pure function of `(input hashes, oracle version hash, config hash)` and nothing else. This single sentence subsumes every separate prohibition on ledger history, selector scores, learned models, operator confidence, and incident counts reaching a verdict. The grounding document explicitly rejects static information-flow analysis for this, on the grounds that it is undecidable in Python with dynamic imports and file IO. The test is a sandboxed replay instead.

**PC-1:** no persisted or exported field may be a reduction over more than one run's verdicts. Per-artifact and per-run history stays unbounded and fully retained; per-person rates, streaks, risk bands, consistency indices, and trend lines do not exist in the schema. Grounded in Anda, Porter and Brown 2020, the ACE instrument's own co-author publishing its bound, and Baldwin et al. 2021 measuring AUC between 0.5 and 0.6 for 11 of 19 outcomes: a strong population signal can be near-useless as an individual classifier.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_accept_path_purity.py`:

```python
import json
import shutil

from harness.gate import run_gate


def test_the_verdict_does_not_depend_on_any_ledger(tmp_path):
    """A verdict is a pure function of inputs, oracle version, and config.

    Run the gate, destroy every record it produced, run it again. If any
    accumulated history reached the accept path, the second verdict or hash
    would differ.
    """
    first = run_gate(tmp_path / "run1")

    ledger_like = [tmp_path / "run1"]
    for p in ledger_like:
        shutil.rmtree(p, ignore_errors=True)

    second = run_gate(tmp_path / "run2")

    assert second.verdict == first.verdict
    assert second.envelope_hash == first.envelope_hash
    assert second.group_signal_hash == first.group_signal_hash


def test_a_prior_failing_record_does_not_change_a_later_verdict(tmp_path):
    """History must not be able to condemn or absolve a later candidate."""
    clean = run_gate(tmp_path / "clean")

    poisoned = tmp_path / "poisoned"
    poisoned.mkdir(parents=True, exist_ok=True)
    (poisoned / "gate_envelope.json").write_text(
        json.dumps({"task_id": "gate-matmul-2x2x2", "candidate": "garbage",
                    "verdict": "FAIL", "oracle_output_hash": "deadbeef"}),
        encoding="utf-8")
    after = run_gate(poisoned)

    assert after.verdict == clean.verdict
    assert after.envelope_hash == clean.envelope_hash
```

Create `tests/test_no_aggregate_over_the_person.py`:

```python
import ast
from pathlib import Path

HARNESS = Path(__file__).resolve().parent.parent / "harness"

# Names whose subject is the human rather than the work. A field counting
# artifacts is fine; a field scoring a person is not, at any granularity,
# including per-workspace and per-device keys.
FORBIDDEN_SUBSTRINGS = (
    "operator_score", "user_score", "operator_rate", "user_rate",
    "streak", "days_since", "last_seen", "consistency_index",
    "risk_band", "operator_percentile", "user_percentile",
    "operator_trend", "user_trend", "operator_accuracy", "user_accuracy",
    "operator_reliability", "user_reliability", "trust_score",
)


def _assigned_and_key_names(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            yield node.id, node.lineno
        elif isinstance(node, ast.Attribute):
            yield node.attr, node.lineno
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.value, node.lineno


def test_no_module_names_a_quantity_whose_subject_is_the_person():
    hits = []
    for p in sorted(HARNESS.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        for name, lineno in _assigned_and_key_names(p):
            low = name.lower()
            for bad in FORBIDDEN_SUBSTRINGS:
                if bad in low:
                    hits.append(f"{p.name}:{lineno} {name}")
    assert hits == [], (
        "a quantity whose subject is the operator rather than the work: "
        + "; ".join(hits))


def test_the_forbidden_list_itself_is_detected():
    # The test must be able to fail, or it proves nothing.
    probe = "operator_score"
    assert any(bad in probe for bad in FORBIDDEN_SUBSTRINGS)
```

- [ ] **Step 2: Run the tests to verify they fail correctly**

Run: `python -m pytest tests/test_accept_path_purity.py tests/test_no_aggregate_over_the_person.py -v`

Expected: `test_accept_path_purity.py` fails only if Task 8 is not yet complete. `test_no_aggregate_over_the_person.py` should PASS immediately on the current tree. That is the expected result, not a broken test: the invariant holds today and this test freezes it. `test_the_forbidden_list_itself_is_detected` proves the check can fire.

If `test_no_aggregate_over_the_person` fails on the existing tree, do not weaken the list. Report the hit, and rename the offending field so its subject is the artifact.

- [ ] **Step 3: Confirm the purity test can fail**

Temporarily edit `harness/gate.py` `run_gate` to read a prior report and alter the verdict:

```python
    prior = out_dir / "gate_report.json"
    if prior.exists():
        steps.append({"step": "poisoned", "note": "history reached the verdict"})
```

then change the returned `verdict` to `"FAIL"` when `prior.exists()`. Run the purity test and confirm it FAILS. Revert the edit with `git checkout harness/gate.py` and confirm it passes again. A test that has never been seen to fail is not evidence.

- [ ] **Step 4: Run both tests green**

Run: `python -m pytest tests/test_accept_path_purity.py tests/test_no_aggregate_over_the_person.py -v`
Expected: PASS, 4 passed

- [ ] **Step 5: Add both to the CI Phase 0 slice**

In `.github/workflows/ci.yml`, add these two lines to the `Phase 0 slice` step's file list, after `tests/test_file_gate.py`:

```
          tests/test_accept_path_purity.py
          tests/test_no_aggregate_over_the_person.py
```

- [ ] **Step 6: Commit**

```bash
git add tests/test_accept_path_purity.py tests/test_no_aggregate_over_the_person.py .github/workflows/ci.yml
git commit -m "test: freeze accept-path purity and the no-aggregate-over-the-person invariant"
```

---

## Self-Review

**Spec coverage.** Phase 0 in the spec calls for: CI matrix with clean-clone verify (Task 9), stdlib import-graph assertion (Task 9), file gate burn-down (Task 9), orphan check (deferred, see below), AST no-execution scan (deferred to Phase 1 with `certificates/`, which does not exist yet), license split (deferred, see below), `verdict.py` (Task 1), Oracle Protocol widening (Task 2), `run_env` allowlist (Task 3), argv-not-shell and `start_new_session` (deferred, see below), gateway token and Host allowlist and Content-Type (Task 7), and the acceptance gate chain (Task 8). Two spec items outside the stated Phase 0 list are pulled in because the gate depends on them: `advantages.py` (Task 4) and the group-sampling fix (Task 5), both of which the panel identified as live defects on the exact path Task 8 exercises. Task 6 (verdict in the preimage) is likewise pulled forward because Task 8's re-witness step is meaningless if a verdict flip breaks no hash.

**Deliberately deferred from Phase 0, with reasons:**
- The **orphan check** is deferred to Phase 1: Phase 0 creates `verdict.py` and `advantages.py`, which are imported, and `gate.py`, which is reachable only from the CLI. Writing an importer-graph rule that correctly treats CLI entry points is its own task and would gate itself.
- **argv-not-shell and `start_new_session`** in `PytestOracle` are deferred to Phase 1's certificate work. They change the process model of the only oracle that executes candidate code, and the Phase 0 gate deliberately uses an oracle that executes nothing. Doing it alongside the certificate checkers keeps the process-model change in one reviewable slice. The environment allowlist (Task 3), which is the part that protects secrets, ships now.
- The **license split** is a repository-wide metadata change with no test; it belongs in the same commit as the first public artifact, in Phase 3, and is recorded in the spec.

**Placeholder scan.** No TBD, TODO, "handle edge cases", or "similar to Task N" appears. Every code step shows complete code. Every command shows expected output.

**Type consistency.** `Verdict`, `Execution`, `Attribution`, `is_dispositive`, `attribution_for` are defined in Task 1 and used with those exact names in Tasks 2, 5, and 8. `advantages(rewards, estimator)` is defined in Task 4 and called as `_advantages(...)` in Task 5 via the aliased import shown there. `OracleResult` gains `verdict_`, `execution`, `attribution` in Task 2 and Task 5 reads `res.verdict()` and `res.attribution`, both of which Task 2 produces. `run_gate(out_dir)` and `rewitness_envelope(path)` are defined in Task 8 and used in that task's tests only. `over_gate` and `load_grandfathered` are defined in Task 9 and used in that task's tests only.

**One known interaction to watch during execution:** Task 2 changes `OracleResult` from a plain `@dataclass` to a class with an explicit `__init__`. Any existing code constructing it **positionally** will break, because the field order changed (`cmd` is now first, `passed` is now keyword-only). Task 2 Step 5 runs the reverse-import slice specifically to catch this. If breakage is widespread, the cheaper fix is to keep `passed` as the first positional parameter; the tests in Task 2 pass either way.

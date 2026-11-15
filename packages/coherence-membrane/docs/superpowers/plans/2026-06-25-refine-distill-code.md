# refine distill (code) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `distill` to coherence-membrane: verified compression of code, where a denser candidate is accepted only if it preserves behavior (tests) and does not worsen readability, with the density gain reported and the whole judgment carried as a re-checkable witness.

**Architecture:** A thin layer over `refine`. Compression is criterion-preserving compression: the model (or any source) PROPOSES a denser candidate in the `generate` step; the deterministic graders VERIFY it. Two opposing objective graders, `density` (rewards fewer bytes) and `readability` (penalizes over-density: long lines, deep nesting), so a code-golfed candidate cannot score better than a clear one. A hard `guard` carries behavior: the tests must pass. Verify-once is `refine` with `max_iter=1`; an auto-iterating loop is the same call with a real `generate` and `max_iter>1`. The spec is `project-docs/specs/SPEC-refine-efficiency-organ.md`.

**Tech Stack:** Python 3.11+, standard library only. Reuses `coherence_membrane.refine`. Tests in pytest.

## Global Constraints

- Zero runtime dependencies, standard library only. No third-party import.
- No model in the checking step. The graders and guard are deterministic; any generation lives in the caller-supplied `generate` callback.
- Deterministic: identical (original, candidate) yields an identical verdict, gain, and witness hash on any OS.
- Fail-closed: a grader, guard, or subprocess that raises degrades to an honest non-correct outcome, never a crash and never a false pass (mirror `refine`'s contract and `grade`'s fail-closed rule).
- Not code-golf: readability is a gated grader, so a shorter-but-cramped candidate is rejected.
- No em-dashes (U+2014) anywhere, including comments, docstrings, and strings.

## File Structure

- Create `src/coherence_membrane/distill.py`: the readability metric, the two graders, the behavior guard runner, the `distill_code` wiring, and the witness record.
- Create `src/coherence_membrane/distill_cli.py` (or extend an existing CLI if one is found): the `distill --code` subcommand.
- Create `tests/test_distill.py`: unit tests for the metric, graders, guard, wiring, and CLI.

---

### Task 1: Readability cost metric

**Files:**
- Create: `src/coherence_membrane/distill.py`
- Test: `tests/test_distill.py`

**Interfaces:**
- Produces: `readability_cost(text: str) -> float` (lower is easier to read).

- [ ] **Step 1: Write the failing test**

```python
from coherence_membrane.distill import readability_cost

def test_readability_cost_penalizes_code_golf_over_clear():
    clear = "def f(x):\n    y = x + 1\n    return y\n"
    golf = "def f(x):\n return (lambda y:y)(x+1) if x else (x+1)+0+0+0+0+0+0+0+0+0+0+0+0\n"
    # the golfed line is shorter in lines but crammed; clear must score lower (better)
    assert readability_cost(clear) < readability_cost(golf)

def test_readability_cost_is_deterministic():
    t = "a = 1\n    b = 2\n"
    assert readability_cost(t) == readability_cost(t)

def test_readability_cost_empty_is_zero_floor():
    assert readability_cost("") == 0.0
```

- [ ] **Step 2: Run, verify it fails** (`pytest tests/test_distill.py -k readability -v`, expect ImportError / fail).

- [ ] **Step 3: Implement**

```python
"""distill: verified compression of code (and later prose), as graders on refine.

Compression is criterion-preserving: a candidate is accepted only when the
declared criterion survives. The model proposes; these deterministic graders
verify. No model in the checking step.
"""
from __future__ import annotations


def readability_cost(text: str) -> float:
    """A deterministic reconstruction-time proxy. Lower is easier to read.

    The cost is the sum of each line's length SQUARED. Squaring makes a long,
    crammed line cost far more than the same characters split across clear lines:
    splitting an 80-column line into two 40-column lines drops the cost (rewarded),
    joining them back raises it (penalized). So a code-golfed candidate (logic
    crammed onto few long lines) scores worse than a clear multi-line one, while a
    short concise line is not punished. Indentation contributes mildly through line
    length, with no perverse reward for nesting. Language-agnostic; refined later.
    """
    return float(sum(len(line) ** 2 for line in text.splitlines()))
```

- [ ] **Step 4: Run, verify pass.**
- [ ] **Step 5: Commit** (`git add -A && git commit -m "feat(distill): deterministic readability cost metric"`).

---

### Task 2: Density and readability graders

**Files:**
- Modify: `src/coherence_membrane/distill.py`
- Test: `tests/test_distill.py`

**Interfaces:**
- Consumes: `readability_cost`, `GradedCriterion` from refine.
- Produces: `density_grader(original_bytes: int) -> GradedCriterion`, `readability_grader(original_cost: float) -> GradedCriterion`. Each grader's `deviation` takes the candidate text and returns a ratio against the original (ideal < 1.0, failing >= 1.0), with `tolerance = 1.0`.

- [ ] **Step 1: Write the failing test**

```python
from coherence_membrane.distill import density_grader, readability_grader, readability_cost
from coherence_membrane.refine import grade

def test_density_grader_rewards_smaller_rejects_bigger():
    orig = "x = 1\n" * 10                       # 60 bytes
    dg = density_grader(len(orig.encode("utf-8")))
    smaller = grade(dg, "x = 1\n" * 5)          # 30 bytes -> ratio 0.5 -> margin 0.5
    bigger = grade(dg, "x = 1\n" * 20)          # ratio 2.0 -> margin -1.0
    assert smaller.ok and smaller.margin > 0
    assert not bigger.ok

def test_readability_grader_rejects_worse_readability():
    orig = "a = 1\nb = 2\n"
    rg = readability_grader(readability_cost(orig))
    worse = grade(rg, "a=1;b=2;" + "z"*200 + "\n")   # one crammed line -> cost up -> margin < 0
    assert not worse.ok
```

- [ ] **Step 2: Run, verify it fails.**

- [ ] **Step 3: Implement** (add `from .refine import GradedCriterion` at the top of `distill.py`, then append)

```python
def _ratio_deviation(numerator_of_candidate, original_value: float):
    """A deviation = candidate_value / original_value. >=0; ideal < 1; >= 1 fails
    at tolerance 1.0. Fail-closed: a zero or negative original yields inf (refine's
    grade then reads it as unmeasurable, never a false pass)."""
    def deviation(candidate_text: str) -> float:
        if original_value <= 0:
            return float("inf")
        return numerator_of_candidate(candidate_text) / original_value
    return deviation


def density_grader(original_bytes: int) -> GradedCriterion:
    return GradedCriterion(
        "density", "objective",
        _ratio_deviation(lambda t: len(t.encode("utf-8")), float(original_bytes)),
        1.0,
    )


def readability_grader(original_cost: float) -> GradedCriterion:
    return GradedCriterion(
        "readability", "objective",
        _ratio_deviation(readability_cost, original_cost),
        1.0,
    )
```

- [ ] **Step 4: Run, verify pass.**
- [ ] **Step 5: Commit.**

---

### Task 3: Behavior guard (tests runner, fail-closed)

**Files:**
- Modify: `src/coherence_membrane/distill.py`
- Test: `tests/test_distill.py`

**Interfaces:**
- Produces: `command_guard(cmd: str | None) -> Callable[[object], bool]`. Returns a guard that runs `cmd` in a shell and returns True on exit 0. `cmd=None` returns a guard that is always True (behavior unchecked, for callers verifying readability/density only). Any subprocess error returns False (fail-closed: cannot confirm behavior is never "behavior preserved").

- [ ] **Step 1: Write the failing test**

```python
from coherence_membrane.distill import command_guard

def test_command_guard_passes_on_exit_zero():
    assert command_guard("exit 0")(None) is True

def test_command_guard_fails_closed_on_nonzero_and_error():
    assert command_guard("exit 1")(None) is False
    assert command_guard("this_command_does_not_exist_xyz")(None) is False

def test_command_guard_none_is_unchecked_true():
    assert command_guard(None)(None) is True
```

- [ ] **Step 2: Run, verify it fails.**

- [ ] **Step 3: Implement** (add `import subprocess` at the top of `distill.py`, then append)

```python
def command_guard(cmd):
    """A hard guard that runs a behavior check (typically the test suite). True
    only on exit 0. cmd=None leaves behavior unchecked (always True). Fail-closed:
    any launch or timeout error is False, never a false pass. The caller is
    responsible for arranging that cmd exercises the candidate."""
    def guard(_candidate) -> bool:
        if cmd is None:
            return True
        try:
            return subprocess.run(cmd, shell=True, capture_output=True).returncode == 0
        except Exception:
            return False
    return guard
```

- [ ] **Step 4: Run, verify pass.**
- [ ] **Step 5: Commit.**

---

### Task 4: distill_code wiring + witness record

**Files:**
- Modify: `src/coherence_membrane/distill.py`
- Test: `tests/test_distill.py`

**Interfaces:**
- Consumes: `refine`, the graders, `command_guard`.
- Produces: `distill_code(original: str, *, propose=None, candidate=None, behavior_guard=None, max_iter=1) -> dict`. Exactly one of `propose` (a `generate`-style callback `state -> candidate_text`) or `candidate` (a single proposed text, verify-once) must be given. Returns a witness dict: `{"schema": "coherence.distill/1", "verdict": "ACCEPTED"|"REJECTED"|"UNVERIFIABLE", "original_sha256", "candidate_sha256", "original_bytes", "candidate_bytes", "gain", "readability_before", "readability_after", "short_axis", "recheck"}`. `gain = original_bytes / candidate_bytes`. ACCEPTED iff refine returns status "correct" (both graders pass AND guard holds); REJECTED iff a grader/guard rejected a produced candidate; UNVERIFIABLE iff no candidate could be measured.

- [ ] **Step 1: Write the failing test**

```python
import hashlib
from coherence_membrane.distill import distill_code, readability_cost

def test_distill_accepts_a_clean_smaller_candidate():
    original = "def f(x):\n    temp = x + 1\n    result = temp\n    return result\n"
    candidate = "def f(x):\n    return x + 1\n"               # smaller AND simpler
    rec = distill_code(original, candidate=candidate, behavior_guard=None)
    assert rec["verdict"] == "ACCEPTED"
    assert rec["gain"] > 1.0
    assert rec["candidate_sha256"] == hashlib.sha256(candidate.encode("utf-8")).hexdigest()

def test_distill_rejects_code_golf_even_if_smaller():
    original = "def f(x):\n    return x + 1\n"
    golf = "def f(x):return(x+1)"+ "#" + "z"*300 + "\n"        # fewer bytes? force a crammed long line
    rec = distill_code(original, candidate=golf, behavior_guard=None)
    assert rec["verdict"] == "REJECTED"
    assert rec["short_axis"] == "readability"

def test_distill_rejects_when_behavior_guard_fails():
    original = "x = 1\n" * 5
    rec = distill_code(original, candidate="x = 1\n", behavior_guard=lambda c: False)
    assert rec["verdict"] == "REJECTED"
    assert rec["short_axis"] in ("behavior", "density", "readability")  # guard short-circuits correctness
```

Note: in the second test, ensure `golf` is actually fewer bytes than `original` so density passes and only readability rejects; adjust the filler length in implementation if needed so the test asserts the intended axis.

- [ ] **Step 2: Run, verify it fails.**

- [ ] **Step 3: Implement** (add `import hashlib` and `from .refine import refine` at the top of `distill.py`, then append)

```python
def distill_code(original: str, *, propose=None, candidate=None, behavior_guard=None, max_iter=1) -> dict:
    if (propose is None) == (candidate is None):
        raise ValueError("distill_code: pass exactly one of propose= or candidate=")
    original_bytes = len(original.encode("utf-8"))
    original_cost = readability_cost(original)
    graders = [density_grader(original_bytes), readability_grader(original_cost)]
    guard = behavior_guard if behavior_guard is not None else command_guard(None)
    generate = propose if propose is not None else (lambda _state: candidate)
    outcome = refine(
        generate, graders, adjust=lambda _r, s: s, guard=guard,
        target_margin=0.0, cohesion_bar=0.0, max_iter=max_iter,
    )
    cand = outcome.candidate if outcome.candidate is not None else ""
    cand_bytes = len(cand.encode("utf-8"))
    if outcome.status == "correct":
        verdict = "ACCEPTED"
    elif cand:
        verdict = "REJECTED"
    else:
        verdict = "UNVERIFIABLE"
    return {
        "schema": "coherence.distill/1",
        "verdict": verdict,
        "original_sha256": hashlib.sha256(original.encode("utf-8")).hexdigest(),
        "candidate_sha256": hashlib.sha256(cand.encode("utf-8")).hexdigest() if cand else None,
        "original_bytes": original_bytes,
        "candidate_bytes": cand_bytes,
        "gain": round(original_bytes / cand_bytes, 3) if cand_bytes else None,
        "readability_before": round(original_cost, 3),
        "readability_after": round(readability_cost(cand), 3) if cand else None,
        "short_axis": outcome.short_axis,
        "recheck": "coherence-membrane distill --code <original> --candidate <candidate>",
    }
```

Note on `target_margin=0.0, cohesion_bar=0.0`: this is refine's documented degenerate mode (accept any candidate whose every grader margin is >= 0 and the guard holds), which is exactly "behavior preserved AND not worse on density or readability". A future P1.1 may raise the bar to demand a real gain margin.

- [ ] **Step 4: Run, verify pass. Then run the full refine + distill slice** (`pytest tests/test_distill.py tests/test_refine.py -q`).
- [ ] **Step 5: Commit.**

---

### Task 5: CLI `distill --code`

**Files:**
- Create: `src/coherence_membrane/distill_cli.py` (first check for an existing package CLI / `pyproject.toml` `[project.scripts]`; if one exists, add the subcommand there instead and wire the entry point).
- Test: `tests/test_distill.py`

**Interfaces:**
- Consumes: `distill_code`.
- Produces: `main(argv: list[str] | None = None) -> int`. `distill --code --original FILE --candidate FILE --tests "CMD" [--json]`. Reads the two files, builds `command_guard(tests)`, calls `distill_code`, prints a human summary or the JSON record. Exit 0 ACCEPTED, 1 REJECTED, 2 UNVERIFIABLE.

- [ ] **Step 1: Write the failing test**

```python
import json
from coherence_membrane.distill_cli import main

def test_cli_accepts_and_exits_zero(tmp_path, capsys):
    (tmp_path / "a.py").write_text("def f(x):\n    t = x + 1\n    return t\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("def f(x):\n    return x + 1\n", encoding="utf-8")
    rc = main(["--code", "--original", str(tmp_path / "a.py"),
               "--candidate", str(tmp_path / "b.py"), "--json"])
    assert rc == 0
    rec = json.loads(capsys.readouterr().out)
    assert rec["verdict"] == "ACCEPTED" and rec["gain"] > 1.0

def test_cli_rejected_exits_one(tmp_path, capsys):
    (tmp_path / "a.py").write_text("def f(x):\n    return x + 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("def f(x):return(x+1)#" + "z"*300 + "\n", encoding="utf-8")
    rc = main(["--code", "--original", str(tmp_path / "a.py"), "--candidate", str(tmp_path / "b.py")])
    assert rc == 1
```

- [ ] **Step 2: Run, verify it fails.**

- [ ] **Step 3: Implement**

```python
"""CLI for distill: verified code compression."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .distill import command_guard, distill_code


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="distill", description="Verified compression of code.")
    p.add_argument("--code", action="store_true", required=True, help="Code mode (the only mode in P1).")
    p.add_argument("--original", type=Path, required=True)
    p.add_argument("--candidate", type=Path, required=True)
    p.add_argument("--tests", default=None, help="A command that exercises the candidate; exit 0 = behavior preserved.")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    try:
        original = args.original.read_text(encoding="utf-8")
        candidate = args.candidate.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"distill: cannot read input: {exc}")
    rec = distill_code(original, candidate=candidate, behavior_guard=command_guard(args.tests))
    if args.json:
        print(json.dumps(rec, indent=2, sort_keys=True))
    else:
        g = rec["gain"]
        print(f"verdict={rec['verdict']}"
              + (f"  gain={g}x  readability {rec['readability_before']} -> {rec['readability_after']}" if g else ""))
        if rec["verdict"] != "ACCEPTED" and rec["short_axis"]:
            print(f"  short axis: {rec['short_axis']}")
    return {"ACCEPTED": 0, "REJECTED": 1, "UNVERIFIABLE": 2}[rec["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run, verify pass. Run the full suite** (`pytest -q`).
- [ ] **Step 5: Commit, then open the release branch and tag per the project's convention.**

---

## After P1

P2 (prose, declared claims) and P3 (the constellation seam) are scoped in `project-docs/specs/SPEC-refine-efficiency-organ.md`. Do not start them in this plan. When P1 is reviewed and merged, raise the density bar above 0.0 (demand a real gain, not merely "not worse") as a fast follow if review wants it.

"""task_curator.py — admission gates for the N>=100 hard set.

The uplift question stays open until a hard set exists where single-shot does
not saturate (FLAGSHIP-PLAN.md, lane #7), and curation is the slow part. The
failure mode of hand-curating 100 tasks is quality decay: task 87 gets vacuous
tests, task 92 leaks its solution into the prompt, and the eventual eval
measures nothing. This mechanizes admission — a candidate task enters the
registry only through gates, so the set grows across sessions without decaying.

The gates (all must pass to ADMIT; each failure names itself):
  reference_passes   the reference solution passes its own hidden tests
                     (tasks_lib.validate_spec, the existing discipline)
  oracle_can_fail    a derived return-None stub FAILS the hidden tests — the
                     per-task version of "a verifier that cannot fail verifies
                     nothing". Vacuous tests are the quiet killer of pass@k.
  deterministic      the reference passes twice in fresh workdirs (flaky
                     hidden tests would witness DRIFT on honest re-runs)
  no_solution_leak   no substantive solution line appears in the prompt
  edge_coverage      >= MIN_TESTS hidden test functions (edge-heavy by design)
  dedup              task_id and normalized solution body are new vs the
                     existing registries

Fail closed: a solution the stub-deriver cannot parse is REJECTED (no stub, no
falsification check, no admission). Admitted tasks persist as JSONL data, not
code, so the set grows without growing Python files.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .tasks_lib import TaskSpec, materialize, validate_spec

MIN_TESTS = 4
MIN_LEAK_LINE = 16     # solution lines shorter than this are idiom, not leak


def _norm(code: str) -> str:
    return re.sub(r"\s+", "", code)


def _solution_hash(spec: TaskSpec) -> str:
    return hashlib.sha256(_norm(spec.solution).encode()).hexdigest()[:16]


def _stub_solution(solution: str) -> str | None:
    """Replace every top-level function body with `return None`. If there is no
    top-level def to stub, return None (caller fails closed)."""
    lines = solution.splitlines()
    defs = [ln for ln in lines if ln.startswith("def ") and ln.rstrip().endswith(":")]
    if not defs:
        return None
    return "\n".join(f"{d}\n    return None" for d in defs) + "\n"


def _run_with(spec: TaskSpec, work_root: Path, solution_text: str,
              tag: str) -> bool:
    """Materialize the task and run its hidden tests against `solution_text`."""
    import subprocess
    from .oracle import clear_bytecode, run_env
    from .task import load_task
    work = work_root / f"{spec.task_id}-{tag}"
    materialize(spec, work)
    task = load_task(work, workdir=work / "wd")
    task.candidate_full().write_text(solution_text, encoding="utf-8")
    clear_bytecode(Path(task.workdir))
    r = subprocess.run(spec.oracle_cmd, cwd=task.workdir, shell=True,
                       capture_output=True, env=run_env(), timeout=30)
    return r.returncode == 0


def screen(spec: TaskSpec, work_root: str | Path,
           existing: list[TaskSpec] | None = None) -> dict:
    """Run every admission gate. Returns {task_id, admitted, gates: {name:
    "PASS" | "FAIL: reason"}}. Gates are ordered cheap-first; all run so a
    rejection names everything wrong, not just the first thing."""
    work_root = Path(work_root)
    existing = existing or []
    gates: dict[str, str] = {}

    n_tests = len(re.findall(r"^def test_", spec.hidden_tests, re.MULTILINE))
    gates["edge_coverage"] = ("PASS" if n_tests >= MIN_TESTS else
                              f"FAIL: {n_tests} hidden tests < {MIN_TESTS}")

    norm_prompt = _norm(spec.prompt)
    leak = next((ln.strip() for ln in spec.solution.splitlines()
                 if len(ln.strip()) >= MIN_LEAK_LINE
                 and _norm(ln) and _norm(ln) in norm_prompt), None)
    if leak is None and _norm(spec.solution) in norm_prompt:
        leak = "<entire solution body>"     # short solutions leak whole, not by line
    gates["no_solution_leak"] = ("PASS" if leak is None else
                                 f"FAIL: prompt contains solution line {leak!r}")

    ids = {s.task_id for s in existing}
    hashes = {_solution_hash(s) for s in existing}
    if spec.task_id in ids:
        gates["dedup"] = f"FAIL: task_id {spec.task_id!r} already registered"
    elif _solution_hash(spec) in hashes:
        gates["dedup"] = "FAIL: normalized solution duplicates an existing task"
    else:
        gates["dedup"] = "PASS"

    gates["reference_passes"] = ("PASS" if validate_spec(spec, work_root)
                                 else "FAIL: reference solution fails its own tests")

    stub = _stub_solution(spec.solution)
    if stub is None:
        gates["oracle_can_fail"] = ("FAIL: cannot derive a falsification stub "
                                    "(no top-level def) — fail closed")
    elif _run_with(spec, work_root, stub, "stub"):
        gates["oracle_can_fail"] = ("FAIL: return-None stub PASSES the hidden "
                                    "tests — the oracle cannot fail (vacuous)")
    else:
        gates["oracle_can_fail"] = "PASS"

    gates["deterministic"] = ("PASS" if _run_with(spec, work_root, spec.solution,
                                                  "rerun")
                              else "FAIL: reference did not re-pass in a fresh "
                                   "workdir (flaky hidden tests)")

    return {"task_id": spec.task_id,
            "admitted": all(v == "PASS" for v in gates.values()),
            "gates": gates}


def curate(candidates: list[TaskSpec], work_root: str | Path,
           existing: list[TaskSpec] | None = None) -> dict:
    """Screen a batch. Later candidates dedup against earlier ADMITTED ones, so
    one batch cannot admit twins. Returns admitted specs + named rejections."""
    existing = list(existing or [])
    admitted: list[TaskSpec] = []
    rejected: dict[str, dict] = {}
    for spec in candidates:
        r = screen(spec, work_root, existing)
        if r["admitted"]:
            admitted.append(spec)
            existing.append(spec)
        else:
            rejected[spec.task_id] = {k: v for k, v in r["gates"].items()
                                      if v != "PASS"}
    return {"admitted": admitted, "rejected": rejected,
            "admit_rate": round(len(admitted) / max(len(candidates), 1), 3)}


# -- the persisted registry (data, not code) ----------------------------------

def append_registry(specs: list[TaskSpec], registry_path: str | Path) -> int:
    """Append admitted specs as JSONL, each line carrying its content hash so
    later tampering is detectable. Returns the number appended."""
    p = Path(registry_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        for s in specs:
            row = {"task_id": s.task_id, "prompt": s.prompt,
                   "candidate_filename": s.candidate_filename,
                   "solution": s.solution, "hidden_tests": s.hidden_tests,
                   "difficulty": s.difficulty, "oracle_cmd": s.oracle_cmd,
                   "max_new_tokens": s.max_new_tokens}
            row["row_hash"] = hashlib.sha256(
                json.dumps(row, sort_keys=True).encode()).hexdigest()[:16]
            f.write(json.dumps(row, sort_keys=True) + "\n")
    return len(specs)


def load_registry(registry_path: str | Path) -> list[TaskSpec]:
    """Load the curated set, re-checking each row hash (a tampered row is
    dropped loudly rather than silently trained/evaled on)."""
    out: list[TaskSpec] = []
    for line in Path(registry_path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        stored = row.pop("row_hash", "")
        fresh = hashlib.sha256(
            json.dumps(row, sort_keys=True).encode()).hexdigest()[:16]
        if fresh != stored:
            raise ValueError(f"registry row {row.get('task_id')!r} failed its "
                             f"content hash — tampered or corrupted")
        out.append(TaskSpec(**row))
    return out

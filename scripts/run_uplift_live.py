"""run_uplift_live.py -- fire ONE live uplift bench run. An operator command:
It runs a legacy retry diagnostic, not a workflow uplift experiment, and
consumes local model time (and provider quota if hosted names are given);
nothing calls this automatically.

Bare vs wrapped over the hard set (harness/tasks_hard.py), graded by the same
PytestOracle the M7 harness used: the candidate is written into the task's
workdir and the same tests select and score it. Different generation budgets
confound the rate difference. See docs/UPLIFT-EVALUATION.md for alternatives.
Use --out and --work-root to keep run artifacts outside the checkout. Without
--work-root, task work is placed beside --out; the default output directory is
artifacts/uplift/, served read-only by GET /api/uplift.

  python scripts/run_uplift_live.py --providers ollama:qwen2.5:7b --n-candidates 3
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness.oracle import PytestOracle          # noqa: E402
from harness.task import Task                    # noqa: E402
from harness.tasks_hard import HARD_REGISTRY     # noqa: E402
from harness.uplift_bench import run_uplift_bench  # noqa: E402


def load_specs(tasks_file: "str | None") -> list:
    """The 10-task built-in registry, or a curated JSONL lane (e.g.
    tasks/curated/hard_v2.jsonl, 110 tasks) with the same record shape."""
    if not tasks_file:
        return list(HARD_REGISTRY)
    from harness.tasks_lib import TaskSpec
    specs = []
    with open(tasks_file, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            specs.append(TaskSpec(
                task_id=r["task_id"], prompt=r["prompt"],
                candidate_filename=r.get("candidate_filename", "solution.py"),
                solution=r.get("solution", ""),
                hidden_tests=r["hidden_tests"],
                difficulty=r.get("difficulty", "hard"),
                oracle_cmd=r.get("oracle_cmd", "python -m pytest tests/ -q"),
                max_new_tokens=int(r.get("max_new_tokens", 512) or 512)))
    return specs


def prepare(run_root: Path, specs: list,
            lane: str = "tasks_hard") -> tuple[Path, dict]:
    """Materialize the task set: one workdir per task with its hidden tests,
    plus the JSONL the bench loads (named by lane so comparison keys stay
    distinct per lane). Requires a new run root to preserve existing files.
    Task definitions contain executable tests; this is not a code sandbox.
    Returns (jsonl_path, task_id -> Task)."""
    def component(value, field):
        if (not isinstance(value, str)
                or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", value)
                or value.endswith(".")
                or re.fullmatch(r"CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9]",
                                value.split(".")[0], re.IGNORECASE)):
            raise ValueError(f"{field} must be a portable single path component")
        return value.casefold()

    component(lane, "lane")
    seen = set()
    for spec in specs:
        key = component(spec.task_id, "task_id")
        if key in seen or key == f"{lane}.jsonl".casefold():
            raise ValueError("duplicate or reserved task_id")
        seen.add(key)
        if component(spec.candidate_filename, "candidate_filename") == "tests":
            raise ValueError("candidate_filename conflicts with tests directory")
    run_root.mkdir(parents=True, exist_ok=False)
    tasks_by_id: dict = {}
    lines = []
    for spec in specs:
        workdir = run_root / spec.task_id
        (workdir / "tests").mkdir(parents=True, exist_ok=True)
        (workdir / "tests" / "test_solution.py").write_text(
            spec.hidden_tests, encoding="utf-8")
        tasks_by_id[spec.task_id] = Task(
            task_id=spec.task_id, prompt=spec.prompt, oracle="pytest",
            oracle_cmd=spec.oracle_cmd, workdir=str(workdir),
            candidate_path=spec.candidate_filename,
            max_new_tokens=spec.max_new_tokens)
        lines.append(json.dumps(spec.task_json()))
    jsonl = run_root / f"{lane}.jsonl"
    jsonl.write_text("\n".join(lines), encoding="utf-8")
    return jsonl, tasks_by_id


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--providers", default="ollama:qwen2.5:7b",
                    help="comma-separated endpoint[:model] roster names")
    ap.add_argument("--n-candidates", type=int, default=3)
    ap.add_argument("--max-tasks", type=int, default=None)
    ap.add_argument("--tasks-file", default=None,
                    help="curated JSONL lane; default = 10-task built-in set")
    ap.add_argument("--out", default=None)
    ap.add_argument("--work-root", default=None,
                    help="task workspace directory; default is beside --out")
    a = ap.parse_args(argv)
    if a.n_candidates < 1 or (a.max_tasks is not None and a.max_tasks < 1):
        ap.error("candidate and task limits must be positive")

    stamp = time.strftime("%Y%m%d-%H%M%S")
    specs = load_specs(a.tasks_file)
    if a.max_tasks is not None:
        specs = specs[:a.max_tasks]
    lane = Path(a.tasks_file).stem if a.tasks_file else "hard"
    out = Path(a.out) if a.out else (
        ROOT / "artifacts" / "uplift" / f"uplift_{lane}_{stamp}.json")
    run_root = Path(a.work_root) if a.work_root else out.parent / f"work_{stamp}"
    try:
        jsonl, tasks_by_id = prepare(run_root, specs, lane=lane)
    except (ValueError, FileExistsError) as exc:
        ap.error(str(exc))
    graded_oracle = PytestOracle(timeout=60)

    def oracle(candidate: str, tj: dict):
        t = tasks_by_id.get(tj.get("task_id", ""))
        if t is None:
            return None                  # unknown task: unverifiable, honest
        try:
            return graded_oracle.verify(candidate, t).passed
        except Exception:
            return None                  # oracle infra failure, not a fail

    providers = [p.strip() for p in a.providers.split(",") if p.strip()]
    print(f"uplift bench: {len(specs)} tasks ({lane}), "
          f"providers={providers}, n_candidates={a.n_candidates}")
    t0 = time.time()
    doc = run_uplift_bench(jsonl, providers, oracle=oracle,
                           n_candidates=a.n_candidates,
                           max_tasks=a.max_tasks, out_path=out)
    if "error" in doc:
        print(f"error: {doc['error']}")
        return 1
    print(f"done in {time.time() - t0:.0f}s -> {doc.get('artifact_path')}")
    for r in doc["rows"]:
        lo, hi = r["wilson_95"]
        print(f"  {r['provider']:>22} {r['arm']:>7}: "
              f"{r['passes']}/{r['graded']} ({r['pass_rate']:.0%}) "
              f"[{lo:.3f}, {hi:.3f}] "
              f"lat {r['latency_ms_mean'] / 1000:.1f}s "
              f"cand {r['candidates_mean']:.2f} "
              f"unver {r['unverifiable']}")
    for d in doc["deltas"]:
        print(f"  {d['provider']:>22}  descriptive rate difference: "
              f"{d['uplift']:+.0%} -- {d['note']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

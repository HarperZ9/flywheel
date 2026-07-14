"""run_uplift_live.py -- fire ONE live uplift bench run. An operator command:
it consumes local model time (and provider quota if hosted names are given);
nothing calls this automatically.

Bare vs wrapped over the hard set (harness/tasks_hard.py), graded by the same
PytestOracle the M7 harness used: the candidate is written into the task's
workdir and the hidden tests decide. The artifact lands in artifacts/uplift/
where GET /api/uplift serves it read-only.

  python scripts/run_uplift_live.py --providers ollama:qwen2.5:7b --n-candidates 3
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness.oracle import PytestOracle          # noqa: E402
from harness.task import Task                    # noqa: E402
from harness.tasks_hard import HARD_REGISTRY     # noqa: E402
from harness.uplift_bench import run_uplift_bench  # noqa: E402


def prepare(run_root: Path) -> tuple[Path, dict]:
    """Materialize the hard set: one workdir per task with its hidden tests,
    plus the JSONL the bench loads. Returns (jsonl_path, task_id -> Task)."""
    run_root.mkdir(parents=True, exist_ok=True)
    tasks_by_id: dict = {}
    lines = []
    for spec in HARD_REGISTRY:
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
    jsonl = run_root / "tasks_hard.jsonl"
    jsonl.write_text("\n".join(lines), encoding="utf-8")
    return jsonl, tasks_by_id


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--providers", default="ollama:qwen2.5:7b",
                    help="comma-separated endpoint[:model] roster names")
    ap.add_argument("--n-candidates", type=int, default=3)
    ap.add_argument("--max-tasks", type=int, default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_root = ROOT / "artifacts" / "uplift" / f"work_{stamp}"
    out = Path(a.out) if a.out else (
        ROOT / "artifacts" / "uplift" / f"uplift_hard_{stamp}.json")
    jsonl, tasks_by_id = prepare(run_root)
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
    print(f"uplift bench: {len(HARD_REGISTRY)} hard tasks, "
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
        lo, hi = d["newcombe_95"]
        print(f"  {d['provider']:>22}  uplift: {d['uplift']:+.0%} "
              f"[{lo:.3f}, {hi:.3f}] -- {d['note']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

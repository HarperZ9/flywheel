"""run_m7_eval.py — the M7 eval runner. Fires when the trained model lands.

Measures HARNESS LIFT on the held-out task set: verified_inference vs single_shot
of the SAME model, plus flat-N and no-search ablations. Honest scope: this is the
harness's lift over raw single-shot of the local model — NOT "beats frontier"
(that arm needs an external frontier endpoint we do not serve). Writes a
reconstructable M7 scorecard.

Usage (real, after training + `serve.py` with ADAPTER_PATH set to the checkpoint):
    py scripts/run_m7_eval.py --serve http://127.0.0.1:8765 --out m7_scorecard.json
Dry-run (no GPU, proves the runner end-to-end with reference solutions):
    py scripts/run_m7_eval.py --dry-run --out /tmp/m7_dry.json
Pin/compare against a prior scorecard:
    py scripts/run_m7_eval.py ... --pinned prior_scorecard.json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.eval import (run_eval, compare, save_scorecard, load_scorecard,
                          delta_vs_pinned, SINGLE_SHOT, VERIFIED_INFERENCE,
                          FLAT_N, NO_SEARCH)
from harness.oracle import PytestOracle
from harness.proposer import ServeProposer, StubProposer
from harness.tasks_lib import REGISTRY, materialize_all
from harness.tasks_hard import HARD_REGISTRY
from harness.task import load_task

ARMS = [SINGLE_SHOT, VERIFIED_INFERENCE, FLAT_N, NO_SEARCH]


def build_task_set(workroot: Path, n: int, hard: bool = False):
    reg = HARD_REGISTRY if hard else REGISTRY
    dirs = materialize_all(reg[:n], workroot / "m7-tasks")
    return [load_task(d) for d in dirs]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", default="http://127.0.0.1:8765")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--hard", action="store_true", help="use the harder held-out set")
    ap.add_argument("--n-tasks", type=int, default=0)
    ap.add_argument("--out", default="m7_scorecard.json")
    ap.add_argument("--pinned", default="")
    ap.add_argument("--workroot", default=str(Path(__file__).parent.parent / ".m7-run"))
    a = ap.parse_args()

    n = a.n_tasks or (len(HARD_REGISTRY) if a.hard else len(REGISTRY))
    workroot = Path(a.workroot)
    task_set = build_task_set(workroot, n, hard=a.hard)

    if a.dry_run:
        ref = {s.task_id: s.solution for s in REGISTRY}
        def proposer_for(arm, task):
            return StubProposer(ref.get(task.task_id, "pass\n"), model_ref="dry-ref")
        model_ref = "dry-run(reference)"
    else:
        def proposer_for(arm, task):
            return ServeProposer(base_url=a.serve, model_ref="14b-cpt-adapter")
        model_ref = "14b-cpt-adapter"

    def oracle_for(task):
        return PytestOracle()

    reports = run_eval(ARMS, task_set, proposer_for, oracle_for)
    print("=== M7 eval (harness lift on the held-out set) ===")
    for name, r in reports.items():
        print("  " + r.summary())
    verdict = compare(reports)  # verified_inference vs single_shot
    print(f"  verdict (verified_inference >= single_shot): {verdict}")

    meta = {"model_ref": model_ref, "n_tasks": len(task_set),
            "note": "harness lift vs single-shot of the SAME model; not a frontier comparison"}
    save_scorecard(a.out, reports, meta=meta)
    print(f"  scorecard -> {a.out}")

    if a.pinned and Path(a.pinned).exists():
        d = delta_vs_pinned(reports, load_scorecard(a.pinned))
        print(f"  vs pinned {a.pinned}: {d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

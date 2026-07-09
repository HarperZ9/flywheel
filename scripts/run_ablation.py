"""run_ablation.py — the self-authored-criterion ablation (the load-bearing measurement).

Does verified-inference's lift over single-shot come from DIVERSITY (N candidates) or
from SELECTION BY THE EXTERNAL CRITERION? Hold generation fixed; vary only the selector.

  single         : candidate[0], scored on the HIDDEN tests (baseline).
  verified_ext   : best-of-N SELECTED BY the HIDDEN tests, scored on HIDDEN (perfect selector).
  verified_self  : best-of-N SELECTED BY a test the MODEL WROTE ITSELF, scored on HIDDEN.

If verified_self ~ verified_ext, the lift was diversity (externalization does not earn
capability). If verified_self ~ single (lift collapses), the EXTERNAL selector was doing
the work -> externalization earns it. Honest either way; the oracle is the arbiter.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.proposer import ServeProposer
from harness.extract import extract_code
from harness.oracle import PytestOracle
from harness.tasks_lib import materialize_all
from harness.tasks_hard import HARD_REGISTRY
from harness.task import load_task

TEMPS = [0.0, 0.4, 0.8, 1.1]
DEFAULT_SERVE = "http://127.0.0.1:8765"
DEFAULT_WORK = Path(os.environ.get("LOCAL_MODEL_RUN_ROOT", "C:/local-model-run")).expanduser()
WORK = (DEFAULT_WORK / "tmp" / "ablation").resolve()


def run_pytest(workdir: Path, candidate: str, test_src: str) -> bool:
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "solution.py").write_text(candidate)
    td = workdir / "tests"
    td.mkdir(exist_ok=True)
    (td / "test_it.py").write_text(test_src)
    r = subprocess.run([sys.executable, "-m", "pytest", str(td), "-q"],
                       cwd=workdir, capture_output=True, text=True)
    return r.returncode == 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", default=DEFAULT_SERVE, help="local model serve URL")
    ap.add_argument("--workroot", default=str(WORK), help="ablation scratch directory")
    ap.add_argument("--local-model", default="14b-cpt", help="model_ref for local proposer")
    ap.add_argument("--n-tasks", type=int, default=0, help="override number of hard tasks (0=all)")
    args = ap.parse_args()

    work_root = Path(args.workroot).expanduser().resolve()
    work_root.mkdir(parents=True, exist_ok=True)
    prop = ServeProposer(base_url=args.serve, model_ref=args.local_model)
    oracle = PytestOracle()
    task_registry = HARD_REGISTRY
    if args.n_tasks and args.n_tasks > 0:
        task_registry = HARD_REGISTRY[:args.n_tasks]
    dirs = materialize_all(task_registry, work_root / "tasks")
    tasks = [load_task(d) for d in dirs]

    n_single = n_ext = n_self = 0
    self_test_broken = 0
    rows = []
    for i, (task, spec) in enumerate(zip(tasks, task_registry)):
        # 1. generate the candidate pool (fixed generation for all arms)
        cands = []
        for t in TEMPS:
            out = prop.generate(task.prompt, seed=0, temperature=t,
                                max_new_tokens=task.max_new_tokens)
            cands.append(out.text)
        hidden_pass = [oracle.verify(c, task).passed for c in cands]

        # 2. single-shot baseline
        single = hidden_pass[0]

        # 3. verified_ext: best-of-N by HIDDEN tests -> passes hidden iff ANY candidate does
        ext = any(hidden_pass)

        # 4. verified_self: model writes its own test, select by it, score on HIDDEN
        tgen = prop.generate(
            f"Write ONE pytest test function for this task. Import the function from "
            f"`solution`. Output ONLY the test code.\n\nTask: {task.prompt}",
            seed=0, temperature=0.0, max_new_tokens=200)
        self_test = extract_code(tgen.text)
        wd = work_root / f"t{i}"
        # is the self-authored test even runnable on the reference solution?
        if not run_pytest(wd / "ref", spec.solution, self_test):
            self_test_broken += 1
            selected = cands[0]            # broken self-test -> fall back to first candidate
        else:
            selected = next((c for j, c in enumerate(cands)
                             if run_pytest(wd / f"c{j}", c, self_test)), cands[0])
        self_ = oracle.verify(selected, task).passed

        n_single += single; n_ext += ext; n_self += self_
        rows.append(f"  {spec.task_id:16} single={int(single)} ext={int(ext)} self={int(self_)}")

    n = len(tasks)
    print(f"=== self-authored-criterion ablation ({args.local_model}, hard set) ===")
    print("\n".join(rows))
    print(f"\n  single_shot        pass = {n_single}/{n} = {n_single/n:.0%}")
    print(f"  verified_external  pass = {n_ext}/{n} = {n_ext/n:.0%}  (lift +{(n_ext-n_single)/n:.0%})")
    print(f"  verified_self      pass = {n_self}/{n} = {n_self/n:.0%}  (lift +{(n_self-n_single)/n:.0%})")
    print(f"  self-tests broken (fell back): {self_test_broken}/{n}")
    lift_ext = (n_ext - n_single) / n
    lift_self = (n_self - n_single) / n
    print(f"\n  VERDICT: external lift {lift_ext:+.0%} vs self-authored lift {lift_self:+.0%}")
    if lift_ext > 0 and lift_self < lift_ext:
        print("  -> externalization EARNS capability: the external selector recovered lift the")
        print("     self-authored selector did not. (honest: small N, report the numbers)")
    elif lift_self >= lift_ext and lift_ext > 0:
        print("  -> lift SURVIVES self-authored selection: it was DIVERSITY, not externalization.")
    else:
        print("  -> no measurable lift on this set (single-shot saturates or N too small).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

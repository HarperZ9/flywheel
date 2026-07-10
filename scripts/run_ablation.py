"""run_ablation.py — the self-authored-criterion ablation (the load-bearing measurement).

Does verified-inference's lift over single-shot come from DIVERSITY (N candidates) or
from SELECTION BY THE EXTERNAL CRITERION? Hold generation fixed; vary only the selector.

  single         : candidate[0] (temp 0), scored on the HIDDEN tests (baseline).
  verified_ext   : best-of-N SELECTED BY the HIDDEN tests, scored on HIDDEN (perfect selector = pass@N ceiling).
  verified_self  : best-of-N SELECTED BY a test the MODEL WROTE ITSELF, scored on HIDDEN.

If verified_self ~ verified_ext, the lift was diversity (externalization does not earn
capability). If verified_self ~ single (lift collapses), the EXTERNAL selector was doing
the work -> externalization earns it. Honest either way; the oracle is the arbiter.

The uplift question needs headroom: on tasks single-shot already passes there is nothing
to lift. Point this at the curated N>=100 lane (`--registry`) and the difficulty-screen
headroom subset (`--headroom-screen`) to measure where lift can actually appear, against
the trained model over the ollama route (`--ollama-model`). Timing per arm is captured so
the performance cost of any lift is reported, not just the lift.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.proposer import EnterpriseProposer, ServeProposer
from harness.extract import extract_code
from harness.oracle import PytestOracle, _kill_tree
from harness.tasks_lib import materialize_all
from harness.tasks_hard import HARD_REGISTRY
from harness.task_curator import load_registry
from harness.task import load_task

TEMPS = [0.0, 0.4, 0.8, 1.1]
DEFAULT_SERVE = "http://127.0.0.1:8765"
DEFAULT_WORK = Path(os.environ.get("LOCAL_MODEL_RUN_ROOT", "C:/local-model-run")).expanduser()
WORK = (DEFAULT_WORK / "tmp" / "ablation").resolve()


def run_pytest(workdir: Path, candidate: str, test_src: str, timeout: int = 30) -> bool:
    """Tree-killed pytest so a hostile candidate costs one timeout, not a wedge."""
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "solution.py").write_text(candidate, encoding="utf-8")
    td = workdir / "tests"
    td.mkdir(exist_ok=True)
    (td / "test_it.py").write_text(test_src, encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "pytest", str(td), "-q"], cwd=workdir,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    try:
        proc.communicate(timeout=timeout)
        return proc.returncode == 0
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        try:
            proc.communicate(timeout=10)
        except Exception:
            pass
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", default=DEFAULT_SERVE, help="local model serve URL")
    ap.add_argument("--ollama-model", default="",
                    help="route via ollama OpenAI-compat /v1 with an honest model_ref")
    ap.add_argument("--ollama-url", default="http://127.0.0.1:11434/v1")
    ap.add_argument("--registry", default="",
                    help="curated JSONL registry (default: the 10-task HARD_REGISTRY)")
    ap.add_argument("--headroom-screen", default="",
                    help="difficulty-screen JSON; restrict to its headroom_at_temp0 tasks")
    ap.add_argument("--workroot", default=str(WORK), help="ablation scratch directory")
    ap.add_argument("--local-model", default="14b-cpt", help="model_ref for serve proposer")
    ap.add_argument("--n-tasks", type=int, default=0, help="cap number of tasks (0=all)")
    ap.add_argument("--out", default="", help="write a JSON artifact of the result")
    ap.add_argument("--resume", action="store_true",
                    help="skip tasks already in <out>.partial.jsonl")
    args = ap.parse_args()

    work_root = Path(args.workroot).expanduser().resolve()
    work_root.mkdir(parents=True, exist_ok=True)

    if args.ollama_model:
        prop = EnterpriseProposer(base_url=args.ollama_url, model=args.ollama_model,
                                  api_key_env="OLLAMA_API_KEY", model_ref="ollama")
        model_ref = f"ollama:{args.ollama_model}"
    else:
        prop = ServeProposer(base_url=args.serve, model_ref=args.local_model)
        model_ref = args.local_model
    oracle = PytestOracle()

    task_registry = (load_registry(args.registry) if args.registry else list(HARD_REGISTRY))
    if args.headroom_screen:
        screen = json.loads(Path(args.headroom_screen).read_text(encoding="utf-8"))
        headroom = set(screen.get("headroom_at_temp0", []))
        task_registry = [s for s in task_registry if s.task_id in headroom]
    if args.n_tasks and args.n_tasks > 0:
        task_registry = task_registry[:args.n_tasks]

    dirs = materialize_all(task_registry, work_root / "tasks")
    tasks = [load_task(d) for d in dirs]

    partial = Path(str(args.out) + ".partial.jsonl") if args.out else None
    done: dict[str, dict] = {}
    if args.resume and partial and partial.exists():
        for line in partial.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                done[r["task_id"]] = r
        print(f"resume: {len(done)} tasks preloaded", flush=True)

    n_single = n_ext = n_self = 0
    self_test_broken = 0
    gen_s = ver_s = 0.0
    rows_out: list[dict] = []
    for i, (task, spec) in enumerate(zip(tasks, task_registry)):
        if spec.task_id in done:
            r = done[spec.task_id]
        else:
            t_gen = time.monotonic()
            cands = []
            for t in TEMPS:
                out = prop.generate(task.prompt, seed=0, temperature=t,
                                    max_new_tokens=task.max_new_tokens)
                cands.append(out.text)
            gen_dt = time.monotonic() - t_gen

            t_ver = time.monotonic()
            hidden_pass = [oracle.verify(c, task).passed for c in cands]
            single = hidden_pass[0]
            ext = any(hidden_pass)

            tgen = prop.generate(
                f"Write ONE pytest test function for this task. Import the function from "
                f"`solution`. Output ONLY the test code.\n\nTask: {task.prompt}",
                seed=0, temperature=0.0, max_new_tokens=200)
            self_test = extract_code(tgen.text)
            wd = work_root / f"t{i}"
            broken = not run_pytest(wd / "ref", spec.solution, self_test)
            if broken:
                selected = cands[0]
            else:
                selected = next((c for j, c in enumerate(cands)
                                 if run_pytest(wd / f"c{j}", c, self_test)), cands[0])
            self_ = oracle.verify(selected, task).passed
            ver_dt = time.monotonic() - t_ver

            r = {"task_id": spec.task_id, "single": bool(single), "ext": bool(ext),
                 "self": bool(self_), "self_test_broken": bool(broken),
                 "gen_s": round(gen_dt, 2), "ver_s": round(ver_dt, 2)}
            if partial:
                with partial.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(r) + "\n")

        n_single += r["single"]; n_ext += r["ext"]; n_self += r["self"]
        self_test_broken += r["self_test_broken"]
        gen_s += r["gen_s"]; ver_s += r["ver_s"]
        rows_out.append(r)
        print(f"  [{i+1}/{len(tasks)}] {r['task_id']:18} "
              f"single={int(r['single'])} ext={int(r['ext'])} self={int(r['self'])}",
              flush=True)

    n = len(tasks)
    lift_ext = (n_ext - n_single) / n if n else 0.0
    lift_self = (n_self - n_single) / n if n else 0.0
    if lift_ext > 0 and lift_self < lift_ext:
        verdict = "externalization EARNS capability (external selector recovered lift the self-authored one did not)"
    elif lift_self >= lift_ext and lift_ext > 0:
        verdict = "lift SURVIVES self-authored selection: it was DIVERSITY, not externalization"
    else:
        verdict = "no measurable lift on this set (single-shot saturates or N too small)"

    report = {
        "schema": "flywheel.ablation.self-criterion/v1",
        "model_ref": model_ref, "n_tasks": n, "temps": TEMPS,
        "registry": Path(args.registry).name if args.registry else "tasks_hard.HARD_REGISTRY",
        "headroom_screen": Path(args.headroom_screen).name if args.headroom_screen else "",
        "single_shot": {"passed": n_single, "rate": round(n_single / n, 4) if n else 0},
        "verified_external": {"passed": n_ext, "rate": round(n_ext / n, 4) if n else 0,
                              "lift_over_single": round(lift_ext, 4)},
        "verified_self": {"passed": n_self, "rate": round(n_self / n, 4) if n else 0,
                          "lift_over_single": round(lift_self, 4)},
        "self_tests_broken": self_test_broken,
        "compute": {"gen_seconds": round(gen_s, 1), "verify_seconds": round(ver_s, 1),
                    "verified_cost_multiple": len(TEMPS),
                    "note": "verified arms spend len(temps)x generation; single spends 1x"},
        "verdict": verdict,
        "per_task": rows_out,
    }
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=1), encoding="utf-8")

    print(f"\n=== self-authored-criterion ablation ({model_ref}) ===")
    print(f"  single_shot        {n_single}/{n} = {report['single_shot']['rate']:.0%}")
    print(f"  verified_external  {n_ext}/{n} = {report['verified_external']['rate']:.0%}  (lift {lift_ext:+.0%})")
    print(f"  verified_self      {n_self}/{n} = {report['verified_self']['rate']:.0%}  (lift {lift_self:+.0%})")
    print(f"  self-tests broken (fell back): {self_test_broken}/{n}")
    print(f"  compute: {gen_s:.0f}s generation + {ver_s:.0f}s verify; verified arms = {len(TEMPS)}x gen cost")
    print(f"  VERDICT: {verdict}")
    if args.out:
        print(f"  -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

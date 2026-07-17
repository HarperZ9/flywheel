"""run_passn_curve.py -- characterize the pass@N budget curve.

For oracle-free selection (consensus/MBR-exec), the hard ceiling is
correct_count >= 2 among the N candidates. This script measures how that
ceiling moves as N grows: at each budget level (N=4,8,16,32), generate N
candidates and count how many pass the hidden oracle. The resulting curve
tells us whether scaling candidates unlocks the consensus path or whether
the 14B simply cannot produce multiple correct solutions at any budget.

The measurement is FREE from the selector_comparison_headroom run: we
already have 4 candidates per task. For N>4 we need new generations at
additional temperatures/seeds. The curve separates the "need a better
selector" question from the "need more candidates" question.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.proposer import EnterpriseProposer
from harness.extract import extract_code
from harness.oracle import PytestOracle, _kill_tree
from harness.task_curator import load_registry
from harness.tasks_lib import materialize_all
from harness.task import load_task

DEFAULT_WORK = Path(os.environ.get("LOCAL_MODEL_RUN_ROOT", "E:/local-model-run/work")).expanduser()
WORK = (DEFAULT_WORK / "tmp" / "passn").resolve()

BUDGET_LEVELS = [4, 8, 16, 32]

# Genuine diversity up to N=64. Index 0 is the greedy baseline (temp 0 is
# deterministic, so it appears exactly ONCE — no wasted slots). Indices 1..n-1
# walk a (hot temperature x seed) grid so every candidate has a UNIQUE
# (temperature, seed) pair. This is the fix that lets N actually rise past 16:
# the old pool repeated its 16 pairs, so N>16 generated duplicates and added no
# multiplicity. 9 hot temps x 8 seeds = 72 unique hot pairs -> supports N up to 73.
_HOT_TEMPS = [0.2, 0.35, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1]   # 9 distinct
_SEEDS = [0, 42, 137, 7, 2024, 99, 314, 11]                    # 8 distinct


def gen_params(n: int) -> list[dict]:
    """n generation params with UNIQUE (temperature, seed) pairs, INDEX-STABLE
    (gen_params(N)[i] == gen_params(M)[i] for all i < min(N,M)), so a run can be
    extended to a higher N by generating only the new tail indices."""
    params = [{"temperature": 0.0, "seed": 0}]
    for i in range(n - 1):
        temp = _HOT_TEMPS[i % len(_HOT_TEMPS)]
        seed = _SEEDS[(i // len(_HOT_TEMPS)) % len(_SEEDS)]
        params.append({"temperature": temp, "seed": seed})
    return params[:n]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ollama-model", required=True)
    ap.add_argument("--ollama-url", default="http://127.0.0.1:11434/v1")
    ap.add_argument("--registry", required=True)
    ap.add_argument("--headroom-screen", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--max-n", type=int, default=16,
                    help="highest budget level to run (default 16)")
    ap.add_argument("--n-tasks", type=int, default=0)
    args = ap.parse_args()

    levels = [b for b in BUDGET_LEVELS if b <= args.max_n]
    if args.max_n not in levels:
        levels.append(args.max_n)
    max_n = max(levels)
    all_params = gen_params(max_n)

    prop = EnterpriseProposer(base_url=args.ollama_url, model=args.ollama_model,
                              api_key_env="OLLAMA_API_KEY", model_ref="ollama")
    oracle = PytestOracle()

    screen = json.loads(Path(args.headroom_screen).read_text(encoding="utf-8"))
    headroom = set(screen.get("headroom_at_temp0", []))
    task_registry = [s for s in load_registry(args.registry) if s.task_id in headroom]
    if args.n_tasks and args.n_tasks > 0:
        task_registry = task_registry[:args.n_tasks]

    work_root = WORK
    work_root.mkdir(parents=True, exist_ok=True)
    dirs = materialize_all(task_registry, work_root / "tasks")
    tasks = [load_task(d) for d in dirs]

    partial = Path(str(args.out) + ".partial.jsonl")
    done: dict[str, dict] = {}
    if args.resume and partial.exists():
        for line in partial.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                done[r["task_id"]] = r
        print(f"resume: {len(done)} tasks preloaded", flush=True)

    rows = []
    for i, (task, spec) in enumerate(zip(tasks, task_registry)):
        cached = done.get(spec.task_id)
        have = list(cached["passes"]) if cached else []
        if len(have) >= max_n:
            rows.append(cached)
            print(f"  [{i+1}/{len(tasks)}] {spec.task_id:18} (cached, {len(have)} cands)", flush=True)
            continue

        # Fresh, or EXTEND a shorter cached row: generate only the tail indices
        # [len(have), max_n). Index-stable params guarantee the tail lines up.
        start = len(have)
        t0 = time.monotonic()
        new_cands = []
        for p in all_params[start:max_n]:
            out = prop.generate(task.prompt, seed=p["seed"],
                                temperature=p["temperature"],
                                max_new_tokens=task.max_new_tokens)
            new_cands.append(out.text)
        gen_dt = time.monotonic() - t0

        t1 = time.monotonic()
        new_passes = [oracle.verify(c, task).passed for c in new_cands]
        ver_dt = time.monotonic() - t1

        passes = have + [bool(p) for p in new_passes]

        curve = {}
        for n in levels:
            subset = passes[:n]
            curve[str(n)] = {
                "correct_count": sum(subset),
                "any_pass": any(subset),
                "multi_correct": sum(subset) >= 2,
            }

        r = {
            "task_id": spec.task_id,
            "passes": passes,
            "curve": curve,
            "gen_s": round((cached.get("gen_s", 0.0) if cached else 0.0) + gen_dt, 2),
            "ver_s": round((cached.get("ver_s", 0.0) if cached else 0.0) + ver_dt, 2),
            "extended_from": start if start else None,
        }
        rows.append(r)
        with partial.open("a", encoding="utf-8") as f:
            f.write(json.dumps(r) + "\n")

        cc = sum(passes)
        ext_note = f" (extended {start}->{max_n})" if start else ""
        print(f"  [{i+1}/{len(tasks)}] {spec.task_id:18} "
              f"correct={cc}/{max_n} "
              f"{'CONSENSUS-REACHABLE' if cc >= 2 else ('ORACLE-ONLY' if cc >= 1 else 'UNREACHABLE')}"
              f"{ext_note}",
              flush=True)

    n_tasks = len(rows)
    report = {
        "schema": "flywheel.passn_curve/v1",
        "model_ref": f"ollama:{args.ollama_model}",
        "n_tasks": n_tasks,
        "budget_levels": levels,
        "max_n": max_n,
        "curve_summary": {},
    }
    for n in levels:
        any_pass = sum(1 for r in rows if r["curve"][str(n)]["any_pass"])
        multi = sum(1 for r in rows if r["curve"][str(n)]["multi_correct"])
        report["curve_summary"][str(n)] = {
            "pass_at_n": any_pass,
            "pass_at_n_rate": round(any_pass / n_tasks, 4) if n_tasks else 0,
            "consensus_reachable": multi,
            "consensus_reachable_rate": round(multi / n_tasks, 4) if n_tasks else 0,
        }

    report["per_task"] = rows

    Path(args.out).write_text(json.dumps(report, indent=1), encoding="utf-8")

    print(f"\n=== pass@N budget curve ({args.ollama_model}, {n_tasks} headroom tasks) ===")
    for n in levels:
        s = report["curve_summary"][str(n)]
        print(f"  N={n:2d}: pass@N={s['pass_at_n']}/{n_tasks} ({s['pass_at_n_rate']:.0%})  "
              f"consensus-reachable={s['consensus_reachable']}/{n_tasks} ({s['consensus_reachable_rate']:.0%})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

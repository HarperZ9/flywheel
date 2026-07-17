"""Post-process a pass@N curve artifact to score the type-aware consensus
selector at each budget level.

Reads the passn_curve artifact (which has per-candidate pass/fail from the
hidden oracle), regenerates candidates at the same params, runs consensus_select
with the type-aware battery at each N, and reports: at N=4/8/16, how many tasks
does the improved consensus selector actually capture?

This separates the "how many correct exist" (pass@N) from "can consensus find
them" question, measured on the same candidate pool.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.oracle import PytestOracle
from harness.proposer import EnterpriseProposer
from harness.task_curator import load_registry, _fn_name, _fn_arity
from harness.tasks_lib import materialize_all
from harness.task import load_task
from scripts.run_ablation import consensus_select, _infer_param_types
from scripts.run_passn_curve import gen_params

DEFAULT_WORK = Path("E:/local-model-run/tmp/passn_cons").resolve()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--curve", required=True, help="passn_curve artifact JSON")
    ap.add_argument("--ollama-model", required=True)
    ap.add_argument("--ollama-url", default="http://127.0.0.1:11434/v1")
    ap.add_argument("--registry", required=True)
    ap.add_argument("--headroom-screen", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    curve_data = json.loads(Path(args.curve).read_text(encoding="utf-8"))
    levels = curve_data["budget_levels"]
    max_n = curve_data["max_n"]
    all_params = gen_params(max_n)
    curve_tasks = {r["task_id"]: r for r in curve_data["per_task"]}

    prop = EnterpriseProposer(base_url=args.ollama_url, model=args.ollama_model,
                              api_key_env="OLLAMA_API_KEY", model_ref="ollama")
    oracle = PytestOracle()

    screen = json.loads(Path(args.headroom_screen).read_text(encoding="utf-8"))
    headroom = set(screen.get("headroom_at_temp0", []))
    task_registry = [s for s in load_registry(args.registry) if s.task_id in headroom]
    task_registry = [s for s in task_registry if s.task_id in curve_tasks]

    work = DEFAULT_WORK
    work.mkdir(parents=True, exist_ok=True)
    dirs = materialize_all(task_registry, work / "tasks")
    tasks_loaded = [load_task(d) for d in dirs]

    partial = Path(str(args.out) + ".partial.jsonl")
    done = {}
    if args.resume and partial.exists():
        for line in partial.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                done[r["task_id"]] = r
        print(f"resume: {len(done)} cached", flush=True)

    rows = []
    for i, (task, spec) in enumerate(zip(tasks_loaded, task_registry)):
        if spec.task_id in done:
            rows.append(done[spec.task_id])
            print(f"  [{i+1}/{len(task_registry)}] {spec.task_id:18} (cached)", flush=True)
            continue

        fn = _fn_name(spec.solution)
        arity = _fn_arity(spec.solution) or 1
        ptypes = _infer_param_types(spec.solution)

        t0 = time.monotonic()
        cands = []
        for p in all_params:
            out = prop.generate(task.prompt, seed=p["seed"],
                                temperature=p["temperature"],
                                max_new_tokens=task.max_new_tokens)
            cands.append(out.text)
        gen_dt = time.monotonic() - t0

        t1 = time.monotonic()
        hidden_pass = [oracle.verify(c, task).passed for c in cands]

        cons_results = {}
        for n in levels:
            subset = cands[:n]
            cidx, conf = consensus_select(subset, fn, arity,
                                          work / f"cons_{spec.task_id}_n{n}",
                                          param_types=ptypes)
            cons_pass = hidden_pass[cidx]
            cons_results[str(n)] = {
                "selected": cidx,
                "confidence": round(conf, 3),
                "oracle_pass": bool(cons_pass),
                "correct_count": sum(hidden_pass[:n]),
                "any_pass": any(hidden_pass[:n]),
            }
        ver_dt = time.monotonic() - t1

        r = {
            "task_id": spec.task_id,
            "hidden_pass": [bool(h) for h in hidden_pass],
            "consensus_at_n": cons_results,
            "param_types": ptypes,
            "gen_s": round(gen_dt, 2),
            "ver_s": round(ver_dt, 2),
        }
        rows.append(r)
        with partial.open("a", encoding="utf-8") as f:
            f.write(json.dumps(r) + "\n")

        cc = sum(hidden_pass)
        cons16 = cons_results.get(str(max_n), {})
        print(f"  [{i+1}/{len(task_registry)}] {spec.task_id:18} "
              f"cc={cc}/{max_n} cons@{max_n}={'P' if cons16.get('oracle_pass') else 'F'} "
              f"conf={cons16.get('confidence', 0):.2f}", flush=True)

    report = {
        "schema": "flywheel.passn_consensus/v1",
        "model_ref": f"ollama:{args.ollama_model}",
        "n_tasks": len(rows),
        "budget_levels": levels,
        "summary": {},
    }
    for n in levels:
        ext = sum(1 for r in rows if r["consensus_at_n"][str(n)]["any_pass"])
        cons = sum(1 for r in rows if r["consensus_at_n"][str(n)]["oracle_pass"])
        single = sum(1 for r in rows if r["hidden_pass"][0])
        report["summary"][str(n)] = {
            "single": single,
            "external_oracle": ext,
            "consensus": cons,
            "consensus_lift": cons - single,
            "recovery": round((cons - single) / max(ext - single, 1), 4),
        }
    report["per_task"] = rows
    Path(args.out).write_text(json.dumps(report, indent=1), encoding="utf-8")

    print(f"\n=== Consensus at raised N ===")
    for n in levels:
        s = report["summary"][str(n)]
        print(f"  N={n:2d}: ext={s['external_oracle']} cons={s['consensus']} "
              f"lift=+{s['consensus_lift']} recovery={s['recovery']:.0%}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

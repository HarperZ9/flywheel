"""Retest consensus on the 11 external-oracle-rescued tasks with the improved
type-aware battery. Reads existing candidates from the consensus run and
re-runs consensus_select with the new battery, reporting the change."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.oracle import PytestOracle
from harness.proposer import EnterpriseProposer
from harness.task_curator import load_registry, _fn_name, _fn_arity
from harness.tasks_lib import materialize_all
from harness.task import load_task
from scripts.run_ablation import consensus_select, _infer_param_types

REGISTRY = Path("C:/dev/local-model/tasks/curated/hard_v2.jsonl")
SCREEN = Path("E:/local-model-run/difficulty_screen_hard_v2_110.json")
CONSENSUS_RESULT = Path("E:/local-model-run/selector_consensus_headroom.json")
TEMPS = [0.0, 0.4, 0.8, 1.1]


def main():
    result = json.loads(CONSENSUS_RESULT.read_text(encoding="utf-8"))
    rescued = [r for r in result["per_task"]
               if r.get("ext") and not r.get("single")]
    rescued_ids = {r["task_id"] for r in rescued}
    print(f"Retesting {len(rescued)} external-oracle-rescued tasks with improved battery\n")

    screen = json.loads(SCREEN.read_text(encoding="utf-8"))
    headroom = set(screen.get("headroom_at_temp0", []))
    all_specs = {s.task_id: s for s in load_registry(str(REGISTRY)) if s.task_id in headroom}

    oracle = PytestOracle()
    prop = EnterpriseProposer(
        base_url="http://127.0.0.1:11434/v1", model="flywheel-local-coder-14b",
        api_key_env="OLLAMA_API_KEY", model_ref="ollama")

    work = Path("E:/local-model-run/tmp/ablation")
    tasks_dir = work / "tasks"

    old_pass = new_pass = 0
    for r in rescued:
        tid = r["task_id"]
        spec = all_specs.get(tid)
        if not spec:
            print(f"  SKIP {tid}: not in registry")
            continue

        dirs = materialize_all([spec], tasks_dir)
        task = load_task(dirs[0])
        fn = _fn_name(spec.solution)
        arity = _fn_arity(spec.solution) or 1
        ptypes = _infer_param_types(spec.solution)
        cc = r.get("correct_count", sum(r.get("hidden_pass", [])))

        cands = [prop.generate(task.prompt, seed=0, temperature=t,
                               max_new_tokens=task.max_new_tokens).text
                 for t in TEMPS]

        old_idx, _ = consensus_select(cands, fn, arity, work / f"rt_old_{tid}", param_types=None)
        old_oracle = oracle.verify(cands[old_idx], task).passed

        new_idx, new_conf = consensus_select(cands, fn, arity, work / f"rt_new_{tid}", param_types=ptypes)
        new_oracle = oracle.verify(cands[new_idx], task).passed

        old_pass += old_oracle
        new_pass += new_oracle

        delta = ""
        if new_oracle and not old_oracle:
            delta = " FIXED"
        elif not new_oracle and old_oracle:
            delta = " REGRESSED"

        print(f"  {tid:25} cc={cc} ptypes={ptypes[:3]}{'...' if len(ptypes) > 3 else ''} "
              f"old=cand[{old_idx}]({'P' if old_oracle else 'F'}) "
              f"new=cand[{new_idx}]({'P' if new_oracle else 'F'}){delta}")

    print(f"\nOLD battery: {old_pass}/{len(rescued)} rescued tasks passed consensus")
    print(f"NEW battery: {new_pass}/{len(rescued)} rescued tasks passed consensus")
    print(f"Delta: +{new_pass - old_pass} tasks")

    new_cons_total = 3 + (new_pass - old_pass)
    print(f"\nProjected full consensus: {new_cons_total}/61 ({new_cons_total/61:.0%})")
    print(f"Recovery of external lift: {new_cons_total - 3}/{14 - 3} = {(new_cons_total - 3)/(14 - 3):.0%}")


if __name__ == "__main__":
    raise SystemExit(main())

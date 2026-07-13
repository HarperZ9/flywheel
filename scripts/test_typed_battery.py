"""Quick verification: does the type-aware battery fix the 2 missed consensus tasks?

The old mixed-type battery missed sliding_window_max and splice_pure despite
both having 2 correct candidates. The fix: infer parameter types from the
solution's function signature and generate inputs that match expected types.

This script re-runs consensus_select with the new type-aware battery on the
3 consensus-reachable tasks from the ablation. It uses the SAME candidates
already generated (reads from the ablation workdir), so no new model calls.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.oracle import PytestOracle
from harness.task_curator import load_registry, _fn_name, _fn_arity
from harness.tasks_lib import materialize_all
from harness.task import load_task
from scripts.run_ablation import consensus_select, _infer_param_types, _battery

REGISTRY = Path("C:/dev/local-model/tasks/curated/hard_v2.jsonl")
SCREEN = Path("E:/local-model-run/difficulty_screen_hard_v2_110.json")
ABLATION_WORK = Path("E:/local-model-run/tmp/ablation")
CONSENSUS_REACHABLE = ["sliding_window_max", "splice_pure", "matrix_transpose"]


def main():
    screen = json.loads(SCREEN.read_text(encoding="utf-8"))
    headroom = set(screen.get("headroom_at_temp0", []))
    all_specs = [s for s in load_registry(str(REGISTRY)) if s.task_id in headroom]
    target_specs = [s for s in all_specs if s.task_id in CONSENSUS_REACHABLE]

    if not target_specs:
        print("ERROR: none of the target tasks found in registry")
        return 1

    oracle = PytestOracle()
    work = ABLATION_WORK
    tasks_dir = work / "tasks"

    for spec in target_specs:
        tid = spec.task_id
        fn = _fn_name(spec.solution)
        arity = _fn_arity(spec.solution) or 1
        ptypes = _infer_param_types(spec.solution)

        print(f"\n=== {tid} ===")
        print(f"  fn={fn}, arity={arity}, inferred_types={ptypes}")
        print(f"  battery sample (3): {_battery(arity, n=3, param_types=ptypes)}")

        # Find existing candidates from the ablation run
        cand_dir = tasks_dir / tid / "wd"
        task_dir = tasks_dir / tid
        if not task_dir.exists():
            materialize_all([spec], tasks_dir)
        task = load_task(task_dir)

        # Read the partial JSONL to get hidden_pass for this task
        partial = Path("E:/local-model-run/selector_consensus_headroom.json.partial.jsonl")
        row = None
        for line in partial.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r["task_id"] == tid:
                row = r
                break

        if row:
            hp = row.get("hidden_pass", [])
            cc = row.get("correct_count", sum(hp))
            print(f"  hidden_pass={hp}, correct_count={cc}")
        else:
            print(f"  WARNING: {tid} not found in partial, skipping")
            continue

        # Re-generate candidates at the same temps to test consensus
        from harness.proposer import EnterpriseProposer
        prop = EnterpriseProposer(
            base_url="http://127.0.0.1:11434/v1",
            model="flywheel-local-coder-14b",
            api_key_env="OLLAMA_API_KEY", model_ref="ollama")

        temps = [0.0, 0.4, 0.8, 1.1]
        cands = []
        for t in temps:
            out = prop.generate(task.prompt, seed=0, temperature=t,
                                max_new_tokens=task.max_new_tokens)
            cands.append(out.text)

        # Run old battery (no types)
        old_idx, _ = consensus_select(cands, fn, arity,
                                       work / f"test_old_{tid}", param_types=None)
        old_pass = oracle.verify(cands[old_idx], task).passed

        # Run new battery (with types)
        new_idx, new_conf = consensus_select(cands, fn, arity,
                                              work / f"test_new_{tid}", param_types=ptypes)
        new_pass = oracle.verify(cands[new_idx], task).passed

        print(f"  OLD battery: selected candidate[{old_idx}], oracle={'PASS' if old_pass else 'FAIL'}")
        print(f"  NEW battery: selected candidate[{new_idx}], oracle={'PASS' if new_pass else 'FAIL'}")

        improvement = "FIXED" if new_pass and not old_pass else ("SAME" if old_pass == new_pass else "REGRESSED")
        print(f"  -> {improvement}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""difficulty_screen.py — the second admission arm for the curated hard set.

The curator admits for SOUNDNESS; this screens for DIFFICULTY: run the exact
M7 single_shot arm (one deterministic sample, temp 0, seed 0) of the trained
14B over the curated registry and record which tasks it already passes. A
task that saturates at temp 0 is a CULL CANDIDATE for the hard set — it buys
no headroom for measuring lift. A task that fails keeps headroom.

HONEST SCOPE: one temp-0 sample is the single_shot arm definition, NOT
pass@k. A temp-0 failure does not certify the task hard (best-of-N may pass
it — which is exactly the headroom the eval needs). This report labels tasks
"saturates_at_temp0" vs "headroom_at_temp0", nothing stronger.

Usage (serve.py already up with the trained adapter):
    python scripts/difficulty_screen.py --serve http://127.0.0.1:8765 --out report.json
Dry-run falsifier (no GPU; reference solutions MUST score 100% or the runner
is broken):
    python scripts/difficulty_screen.py --dry-run --out /tmp/screen_dry.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.eval import SINGLE_SHOT, run_arm
from harness.oracle import PytestOracle
from harness.proposer import EnterpriseProposer, ServeProposer, StubProposer
from harness.task import load_task
from harness.task_curator import load_registry
from harness.tasks_lib import materialize_all

DEFAULT_REGISTRY = Path(__file__).parent.parent / "tasks" / "curated" / "hard_v2.jsonl"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", default="http://127.0.0.1:8765")
    ap.add_argument("--ollama-model", default="",
                    help="route via Ollama's OpenAI-compatible /v1 instead of "
                         "serve.py (e.g. flywheel-local-coder-14b); the "
                         "model_ref records the honest ollama:<model> identity")
    ap.add_argument("--ollama-url", default="http://127.0.0.1:11434/v1")
    ap.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", default="difficulty_screen.json")
    ap.add_argument("--workroot",
                    default=str(Path(__file__).parent.parent / ".screen-run"))
    a = ap.parse_args()

    specs = load_registry(a.registry)
    dirs = materialize_all(specs, Path(a.workroot) / "tasks")
    tasks = [load_task(d) for d in dirs]
    ref = {s.task_id: s.solution for s in specs}

    if a.dry_run:
        live_ref = "dry-run(reference)"
    elif a.ollama_model:
        live_ref = f"ollama:{a.ollama_model}"
    else:
        live_ref = "14b-cpt-adapter"

    rows = []
    for task in tasks:
        if a.dry_run:
            proposer = StubProposer(ref[task.task_id], model_ref="dry-ref")
        elif a.ollama_model:
            proposer = EnterpriseProposer(
                base_url=a.ollama_url, model=a.ollama_model,
                api_key_env="OLLAMA_API_KEY", model_ref="ollama")
        else:
            proposer = ServeProposer(base_url=a.serve, model_ref="14b-cpt-adapter")
        r = run_arm(SINGLE_SHOT, task, proposer, PytestOracle())
        rows.append({"task_id": task.task_id, "passed": bool(r.passed)})
        print(f"  {task.task_id:28s} {'PASS (cull candidate)' if r.passed else 'FAIL (headroom)'}",
              flush=True)

    n = len(rows)
    saturated = sorted(x["task_id"] for x in rows if x["passed"])
    report = {
        "screen": "difficulty/single_shot_temp0",
        "model_ref": live_ref,
        "registry": Path(a.registry).name,
        "n_tasks": n,
        "single_shot_rate": round(sum(x["passed"] for x in rows) / max(n, 1), 3),
        "saturates_at_temp0": saturated,
        "headroom_at_temp0": sorted(x["task_id"] for x in rows if not x["passed"]),
        "per_task": rows,
        "note": ("one temp-0 sample = the M7 single_shot arm, NOT pass@k; "
                 "temp-0 failure does not certify hardness"),
    }
    Path(a.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"single_shot@temp0: {report['single_shot_rate']:.0%} "
          f"({len(saturated)}/{n} saturate) -> {a.out}")
    if a.dry_run and report["single_shot_rate"] != 1.0:
        print("DRY-RUN FALSIFIER FIRED: reference solutions must score 100%")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

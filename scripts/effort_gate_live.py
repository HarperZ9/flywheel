"""effort_gate_live.py -- rerun G4's arms with every search candidate logged.

Same split, model, temperatures and seeds as scripts/run_heldout_rerun.py. For each
task it records the single arm (temperature 0) and all four search candidates, each
with its visible and held-out verdict, so effort_gate_replay.py can replay any gate
exactly by truncating the list.

  python scripts/effort_gate_live.py --registry hard_v2 --model flywheel-local-coder-14b \
      --base-url http://127.0.0.1:11500/v1 --out artifacts/effort-gate/hard_v2.json
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from harness.providers import make_proposer  # noqa: E402
from harness.search import DEFAULT_TEMPS  # noqa: E402
from harness.task import load_task  # noqa: E402
from run_heldout_rerun import _held, _visible, materialize, registry  # noqa: E402


def _sample(proposer, task, seed: int, temp: float) -> tuple[str, dict]:
    start = time.perf_counter()
    out = proposer.generate(task.prompt, seed=seed, temperature=temp,
                            max_new_tokens=task.max_new_tokens, system=task.system)
    usage = out.usage or {}
    return out.text, {"secs": round(time.perf_counter() - start, 3),
                      "prompt_tokens": usage.get("prompt"),
                      "completion_tokens": usage.get("completion")}


def run_task(spec: dict, proposer, scratch: Path) -> dict:
    tdir = materialize(spec, scratch / spec["task_id"])
    row = {"task_id": spec["task_id"]}
    if tdir is None:
        return dict(row, excluded="fewer than two tests")
    task = load_task(tdir, workdir=scratch / "w" / spec["task_id"])
    if not (_visible(spec["solution"], task) and _held(spec["solution"], task)):
        return dict(row, excluded="reference fails a split suite")
    text, cost = _sample(proposer, task, task.seed, task.temperature)
    row.update(single_visible=_visible(text, task), single_held=_held(text, task),
               single_cost=cost, visible=[], held=[], cost=[], same_as_single=[])
    for i, temp in enumerate(DEFAULT_TEMPS):
        cand, cost = _sample(proposer, task, task.seed + i, temp)
        row["visible"].append(_visible(cand, task))
        row["held"].append(_held(cand, task))
        row["cost"].append(cost)
        row["same_as_single"].append(cand == text)
    return row


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", default="hard")
    ap.add_argument("--model", required=True)
    ap.add_argument("--base-url", default="http://127.0.0.1:11434/v1")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    proposer = make_proposer("ollama", model=a.model, base_url=a.base_url)
    scratch = Path(tempfile.mkdtemp(prefix="effort-gate-"))
    rows = []
    try:
        for spec in registry(a.registry):
            rows.append(run_task(spec, proposer, scratch))
            print(json.dumps(rows[-1]), flush=True)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    doc = {"schema": "flywheel.effort-gate-log/v1", "registry": a.registry,
           "model_ref": f"ollama:{a.model}", "temps": DEFAULT_TEMPS, "rows": rows}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(doc, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

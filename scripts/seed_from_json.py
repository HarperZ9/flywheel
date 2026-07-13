#!/usr/bin/env python3
"""seed_from_json.py — admit a JSON candidate batch into the curated registry.

Generic runner for workflow-authored batches: candidates arrive as a JSON list
of {task_id, prompt, solution, hidden_tests}, produced by author agents that
self-verified by execution. Self-verification is NOT admission — every
candidate still goes through the full curator gates here (reference passes,
stub must fail, deterministic, no leak, edge coverage, behavioral dedup vs all
code tiers + the registry + the rest of the batch).

Usage:
    python scripts/seed_from_json.py tasks/curated/batch3_candidates.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from harness.task_curator import seed_batch
from harness.tasks_lib import TaskSpec

REGISTRY_PATH = Path(__file__).parent.parent / "tasks" / "curated" / "hard_v2.jsonl"


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: seed_from_json.py <candidates.json>")
        return 2
    rows = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    batch = [TaskSpec(r["task_id"], r["prompt"], "solution.py", r["solution"],
                      r["hidden_tests"], "hard", max_new_tokens=768)
             for r in rows]
    out = seed_batch(batch, REGISTRY_PATH)
    for tid, bad in out["rejected"].items():
        print(f"REJECTED {tid}: {json.dumps(bad)}")
    print(f"admitted {len(out['admitted'])}/{len(batch)} "
          f"(registry total: {out['registry_total']}; lane target: 100)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

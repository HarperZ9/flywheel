"""quality_duel.py -- the dual-evidence quality run, one command.

Runs the SAME curated task set through two or more provider roles under the
SAME external oracle, and writes a scorecard whose rows carry provider,
provider_role, and measured pass rates -- exactly the dual evidence
`flywheel comparison` requires before any better-than claim can exist.

Honesty is mechanical, not advisory:
- rows are marked evidence="live" only when the providers were real
  (resolved from the roster); injected test proposers mark every row
  evidence="synthetic", and the comparison loader ignores synthetic rows.
- a task whose oracle cannot run is counted unverifiable and excluded from
  the pass-rate denominator, with the exclusion visible in the row.
- the run consumes provider quota, so firing it against hosted or
  CLI-metered roles is an operator decision; nothing imports this module
  and starts one on its own."""
from __future__ import annotations

import json
import time
from pathlib import Path

from .provider_roles import provider_role

SCHEMA = "flywheel.quality-duel-scorecard/v1"


def load_tasks(tasks_path: "Path | str", max_tasks: "int | None" = None) -> list:
    tasks = []
    with open(tasks_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                tasks.append(json.loads(line))
            except ValueError:
                continue
            if max_tasks and len(tasks) >= max_tasks:
                break
    return tasks


def run_quality_duel(tasks_path: "Path | str", providers: list, *,
                     oracle, proposers: "dict | None" = None,
                     max_tasks: "int | None" = None,
                     out_path: "Path | str | None" = None) -> dict:
    """Every provider answers every task; `oracle(candidate, task)` returns
    True/False, or None for unverifiable. `proposers` overrides provider
    resolution for tests and marks the whole run synthetic."""
    tasks = load_tasks(tasks_path, max_tasks)
    if not tasks:
        return {"error": f"no tasks loaded from {tasks_path}"}
    synthetic = proposers is not None
    rows = []
    for name in providers:
        if synthetic:
            proposer = proposers.get(name)
            if proposer is None:
                return {"error": f"no injected proposer for '{name}'"}
        else:
            from .endpoint_registry import make_endpoint_proposer
            proposer = make_endpoint_proposer(name)
        passes = fails = unverifiable = 0
        latencies = []
        for task in tasks:
            t0 = time.perf_counter()
            try:
                out = proposer.generate(
                    task.get("prompt", ""), seed=0, temperature=0.0,
                    max_new_tokens=int(task.get("max_new_tokens", 512) or 512))
                candidate = out.text if isinstance(out.text, str) else str(out.text)
            except Exception:
                fails += 1
                continue
            latencies.append((time.perf_counter() - t0) * 1000)
            verdict = oracle(candidate, task)
            if verdict is None:
                unverifiable += 1
            elif verdict:
                passes += 1
            else:
                fails += 1
        graded = passes + fails
        rows.append({
            "provider": name,
            "provider_role": provider_role(name),
            "evidence": "synthetic" if synthetic else "live",
            "n_tasks": len(tasks),
            "graded": graded,
            "unverifiable": unverifiable,
            "pass_rate": round(passes / graded, 4) if graded else 0.0,
            "quality_score": round(passes / graded, 4) if graded else 0.0,
            "latency_ms": round(sum(latencies) / len(latencies), 3)
                          if latencies else 0.0,
            "failure_class": "" if graded else "nothing_graded",
        })
    doc = {"schema": SCHEMA,
           "comparison_key": f"quality_duel:{Path(str(tasks_path)).stem}",
           "rows": rows,
           "note": "synthetic rows never enter comparison; unverifiable "
                   "tasks are excluded from the denominator and counted"}
    if out_path:
        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(doc, indent=1), encoding="utf-8")
        doc["artifact_path"] = str(p)
    return doc

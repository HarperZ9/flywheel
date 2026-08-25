"""trace_bench.py -- the improvement loop with receipts.

Every stored agent run is a benchmark task waiting to happen: the run's
goal is the prompt, the run's own test command is the gate, and the
recorded verdict is the prior outcome. Convert traces into a verified
task set, re-run it after any model, prompt, or harness change, and the
regression report names exactly which previously-passing task now fails
-- sealed, comparable across runs, and re-checkable offline. Tasks
without a recorded gate command are skipped, never faked.
"""
from __future__ import annotations

import json
from pathlib import Path

from .evidence_json import canonical_sha256

SCHEMA = "flywheel.trace-task-set/v1"


def traces_to_task_set(runs: list[dict], *, out_path: Path | str) -> Path:
    """Emit one verified-bench task per stored run that carries a gate
    command. Runs sharing a goal deduplicate to their newest attempt.
    The task set is written JSONL, loadable by verified_bench.load_task_
    set, and each row records the run's prior verdict."""
    by_key: dict[str, dict] = {}
    for run in runs:
        goal = str(run.get("goal", "")).strip()
        gate_cmd = str(run.get("test_cmd", "")).strip()
        # Stored run details omit their own id (it is the file stem), so
        # an absent id derives from the run's canonical bytes: stable
        # across re-reads, never guessed.
        run_id = str(run.get("run_id") or
                     canonical_sha256(run)[:16]).strip()
        if not goal or not gate_cmd or not run_id:
            continue
        by_key[run_id] = run          # later runs win: newest attempt
    rows = []
    for run_id, run in by_key.items():
        rows.append({
            "task_id": f"trace-{run_id}",
            "prompt": str(run.get("goal", "")).strip(),
            "gate_cmd": run["test_cmd"],
            "prior_verdict": str(run.get("verdict", "UNKNOWN")),
            "endpoint": str(run.get("endpoint", "")),
        })
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(json.dumps(r, sort_keys=True) for r in rows),
                   encoding="utf-8")
    return out


def write_task_set(rows: list[dict], *, out_path: Path | str) -> Path:
    """Persist an already-built task set (the write half of
    traces_to_task_set, exposed for route handlers that assemble rows
    themselves)."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(json.dumps(r, sort_keys=True) for r in rows),
                   encoding="utf-8")
    return out


def regression_report(prior: dict, current: dict) -> dict:
    """Compare two verified benches over the same task set: a regression
    is a previously-passing attempt that now fails; an improvement is the
    reverse; new task ids are reported, never silently dropped."""
    def key(a: dict) -> tuple:
        return (a["task_id"], a["endpoint"])

    prior_by_key = {key(a): a for a in prior.get("attempts", [])}
    current_by_key = {key(a): a for a in current.get("attempts", [])}
    regressions, improvements, stable, new = [], [], 0, []
    for k, cur in current_by_key.items():
        prev = prior_by_key.get(k)
        now = "PASS" if cur["gate_pass"] else "FAIL"
        if prev is None:
            new.append({"task_id": k[0], "endpoint": k[1],
                        "current": now})
        elif prev["gate_pass"] and not cur["gate_pass"]:
            regressions.append({"task_id": k[0], "endpoint": k[1],
                                "prior": "PASS", "current": "FAIL"})
        elif not prev["gate_pass"] and cur["gate_pass"]:
            improvements.append({"task_id": k[0], "endpoint": k[1],
                                 "prior": "FAIL", "current": "PASS"})
        else:
            stable += 1
    return {
        "schema": "flywheel.trace-regression/v1",
        "regressions": regressions,
        "improvements": improvements,
        "stable": stable,
        "new": new,
        "does_not_prove": (
            "a regression is over this task set and these gates only; "
            "flaky gates surface here as regressions, which is the point"),
    }

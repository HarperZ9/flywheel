"""trace_bench_route.py -- the regression loop route.

POST /api/bench/traces: pull failed (or all) stored agent runs from the
run store, convert them into a verified task set, run it across the
ladder's endpoints through real gates, and report regressions against
the prior bench for the same trace set. One route closes the
improvement loop: run -> fail -> bench -> fix -> re-run -> receipt.
"""
from __future__ import annotations

import json
from pathlib import Path

from .evidence_public import TransportError, error_response
from .eval_store import agent_run_detail
from .trace_bench import regression_report, traces_to_task_set
from .verified_bench import run_private_benchmark, verified_frontier

def _invalid(message: str) -> tuple[dict, int]:
    return error_response(TransportError("INVALID_REQUEST", message, 422))


def _collect_traces(run_root: Path, run_ids: list[str] | None,
                    limit: int) -> list[dict]:
    if run_ids:
        runs = [agent_run_detail(run_root, rid) for rid in run_ids]
        return [r for r in runs if "error" not in r]
    listing = json.loads(json.dumps(
        _all_runs(run_root, limit)))
    return [r for r in listing if r.get("intact", True)]


def _all_runs(run_root: Path, limit: int) -> list[dict]:
    from .eval_store import agent_runs
    rows = agent_runs(run_root, limit=limit).get("runs", [])
    detailed = []
    for row in rows:
        detail = agent_run_detail(run_root, row.get("run_id", ""))
        if "error" not in detail:
            detail["run_id"] = row.get("run_id", "")
            detailed.append(detail)
    return detailed


def handle_bench_traces(body: dict, *, run_root: Path,
                        build_endpoints) -> tuple[dict, int]:
    run_ids = body.get("run_ids")
    limit = body.get("limit", 50)
    outcomes = body.get("outcomes", ["FAIL"])
    timeout_s = body.get("timeout_s", 120)
    endpoints = body.get("endpoints")
    if not isinstance(limit, int) or not 1 <= limit <= 500:
        return _invalid("limit is outside 1..500")
    if not isinstance(outcomes, list) or not outcomes:
        return _invalid("outcomes filter is empty")
    if not isinstance(timeout_s, (int, float)) or not 1 <= timeout_s <= 1800:
        return _invalid("timeout_s is outside 1..1800")

    traces = _collect_traces(Path(run_root),
                             run_ids if isinstance(run_ids, list) else None,
                             limit)
    selected = [t for t in traces
                if str(t.get("verdict", "")).upper() in
                {o.upper() for o in outcomes}]
    if not selected:
        return error_response(TransportError(
            "NO_TRACES", "no stored runs match the outcome filter", 404))
    task_set_path = Path(run_root) / "bench" / "trace-tasks.jsonl"
    traces_to_task_set(selected, out_path=task_set_path)
    from .verified_bench import load_task_set
    tasks = load_task_set(task_set_path)

    ladder = build_endpoints(
        providers=endpoints, modes=("plan", "api", "provider", "cloud"))
    if not ladder:
        return _invalid("no ladder endpoints are configured")
    with tempfile_dir(run_root) as work:
        bench = run_private_benchmark(
            tasks=tasks, ladder=ladder, workspace_root=Path(work),
            timeout_s=float(timeout_s),
            created_at=body.get("created_at", ""))

    prior_path = Path(run_root) / "bench" / "trace-bench-prior.json"
    prior = (json.loads(prior_path.read_text(encoding="utf-8"))
             if prior_path.is_file() else {"attempts": []})
    report = regression_report(prior, bench)
    frontier = verified_frontier(bench, cost_per_task=body.get(
        "cost_per_task"))
    # This bench becomes the prior for the next run.
    prior_path.parent.mkdir(parents=True, exist_ok=True)
    prior_path.write_text(json.dumps(bench, indent=2, sort_keys=True),
                          encoding="utf-8")
    return {"schema": "flywheel.trace-bench-run/v1",
            "task_set": str(task_set_path.name),
            "tasks": len(tasks),
            "bench": bench,
            "regressions": report,
            "frontier": frontier}, 200


def tempfile_dir(root: Path):
    import tempfile
    return tempfile.TemporaryDirectory(dir=root)

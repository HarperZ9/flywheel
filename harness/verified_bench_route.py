"""The private-benchmark route: an exact-grant execution that runs a
task set across ladder endpoints and disposes every attempt through a
real subprocess gate. Exec scope is mandatory: gates run commands."""
from __future__ import annotations

import tempfile
from pathlib import Path

from .evidence_public import TransportError, error_response
from .verified_bench import run_private_benchmark, verified_frontier


def _invalid(message: str) -> tuple[dict, int]:
    return error_response(TransportError("INVALID_REQUEST", message, 422))


def handle_bench_run(body: dict, *, run_root: Path,
                     build_endpoints) -> tuple[dict, int]:
    """Run the private benchmark. `authorized` carries the canonical
    operation; the grant already bound tasks, endpoints, and timeout."""
    tasks = body.get("tasks")
    endpoints = body.get("endpoints")
    timeout_s = body.get("timeout_s", 120)
    if not isinstance(tasks, list) or not tasks:
        return _invalid("the benchmark carries no tasks")
    if any(not isinstance(t, dict)
           or any(not isinstance(t.get(k), str) or not t.get(k)
                  for k in ("task_id", "prompt", "gate_cmd"))
           for t in tasks):
        return _invalid("every task needs task_id, prompt, and gate_cmd")
    if len({t["task_id"] for t in tasks}) != len(tasks):
        return _invalid("duplicate task ids")
    if not isinstance(endpoints, list) or not endpoints:
        return _invalid("the benchmark names no endpoints")
    if not isinstance(timeout_s, (int, float)) or not 1 <= timeout_s <= 1800:
        return _invalid("timeout_s is outside 1..1800")
    ladder = build_endpoints(providers=endpoints,
                             modes=("plan", "api", "provider", "cloud"))
    present = {b.name.split("-")[0] for b in ladder}
    missing = [e for e in endpoints
               if e not in present and e.split("-")[0] not in present]
    if missing:
        return _invalid(
            f"endpoints are not configured or lack credentials: {missing}")
    with tempfile.TemporaryDirectory(dir=run_root) as work:
        try:
            bench = run_private_benchmark(
                tasks=tasks, ladder=ladder,
                workspace_root=Path(work), timeout_s=float(timeout_s),
                created_at=body.get("created_at", ""))
        except ValueError as exc:
            return _invalid(str(exc))
        except Exception:
            return error_response(TransportError(
                "BENCH_FAILED", "the benchmark run failed", 500))
    frontier = verified_frontier(bench, cost_per_task=body.get(
        "cost_per_task"))

    # Accountable hooks: fire bench.completed automations from the run
    # root's registry. A failing blocking hook marks the event blocked
    # for downstream automation; the bench itself is sealed either way.
    from .accountable_hooks import (
        event_blocked,
        load_registry,
        run_hooks,
        subprocess_runner,
    )
    registry = load_registry(Path(run_root) / "hooks" / "registry.json")
    hook_receipts = run_hooks(
        "bench.completed", registry,
        runner=subprocess_runner(timeout_s=30.0),
        context={"bench_sha256": bench["bench_sha256"],
                 "endpoints": bench["endpoints"],
                 "attempts": bench["denominator"]["attempts"]})
    return {"schema": "flywheel.verified-bench-run/v1",
            "bench": bench, "frontier": frontier,
            "hook_receipts": hook_receipts,
            "event_blocked": event_blocked(hook_receipts)}, 200

"""fan_out.py — oracle-gated sub-agent fan-out for long-horizon tasks.

Split a large task into independent sub-tasks, run each in an ISOLATED context (its
own workdir, ledger, and oracle), and gather the results in parallel. Sub-agent
fan-out is the field's answer to context-window exhaustion on long tasks. Here each
sub-agent's result carries its own check, and the aggregate reports which sub-tasks
were ACCEPTED, so a fan-out cannot collectively launder an unverified result.

Parallel via stdlib threads (each sub-agent's tool calls are its own subprocess), a
subtask that raises is captured rather than crashing the batch, and results are
returned in input order. Zero-dep.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor


def _safe_run(run_one, spec):
    try:
        return {"ok": True, "spec": spec, "result": run_one(spec)}
    except Exception as e:                                # one bad sub-agent must not sink the batch
        return {"ok": False, "spec": spec, "error": f"{type(e).__name__}: {e}"}


def fan_out(subtasks: list, run_one, *, max_workers: int = 4, accept=None) -> dict:
    """Run run_one(spec) for each spec, in isolated parallel threads. Returns a
    report: per-subtask results in input order plus a summary. `accept(result)`, if
    given, marks which completed sub-results cleared their own check (oracle-gated),
    so `accepted` counts only verified sub-tasks."""
    n = len(subtasks)
    if n == 0:
        return {"schema": "flywheel.fan-out/v1", "n": 0, "completed": 0, "failed": 0,
                "accepted": 0 if accept is not None else None, "results": []}
    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, n))) as ex:
        results = list(ex.map(lambda s: _safe_run(run_one, s), subtasks))
    completed = [r for r in results if r["ok"]]
    if accept is not None:
        # annotate each completed row so the vote count re-derives from the
        # receipt; a raising accept() is a reject on THAT result, never a
        # sunk batch
        for r in completed:
            try:
                r["accepted"] = bool(accept(r["result"]))
            except Exception as e:  # noqa: BLE001 - an accept edge is impure
                r["accepted"] = False
                r["accept_error"] = f"{type(e).__name__}: {e}"
        accepted = sum(1 for r in completed if r.get("accepted") is True)
    else:
        accepted = None
    return {
        "schema": "flywheel.fan-out/v1",
        "n": n,
        "completed": len(completed),
        "failed": n - len(completed),
        "accepted": accepted,
        "results": results,
    }

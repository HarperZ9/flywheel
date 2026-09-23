"""run_budget_deadline.py -- the budget record for a run the deadline stopped.

The aggregate deadline (gateway_agent_deadline) stops the worker's process
tree wherever it is. A run stopped in the middle of a step writes no failure
record, so it has no budget record of its own. The gateway writes one when it
closes the run, from what the private trace shows:

- the limits the approved operation resolves to;
- the model calls and tool actions the trace records, counted the way the
  outcome check counts them, and the harness's check runs apart;
- the tokens and spend the recorded provider responses reported, with each
  model call that recorded none named as a call that reported nothing;
- each model call the trace shows starting (a `model_inference` record in
  phase `started`) with no model_call entry for its ordinal. It was in
  flight when the tree stopped, or failed before it reported usage, so it
  is counted and named as a call that reported nothing;
- a wall-time stop, at the time limit.

What only the worker held in memory is not in the trace and is not claimed:
a Claude CLI message's streamed tokens, a limit error it read, the exact
moment the tree stopped. The record says `recorded_by: gateway_deadline`.
"""
from __future__ import annotations

from .gateway_run_outcome import trace_counts
from .run_budget_contract import DOES_NOT_PROVE, SCHEMA
from .run_budget_usage import reported_cost_micros, reported_tokens

RECORDED_BY = "gateway_deadline"


def _usage(records: list) -> tuple[dict, dict]:
    """Tokens, spend and reporting from the model calls the trace recorded."""
    used = {"usage_tokens": 0, "cost_micros": 0}
    reporting = {"calls_with_tokens": 0, "calls_without_tokens": 0, "calls_with_cost": 0}
    for record in records:
        payload = record.get("payload")
        if (record.get("kind") != "ledger" or type(payload) is not dict
                or payload.get("kind") != "model_call"):
            continue
        meta = payload.get("meta") if type(payload.get("meta")) is dict else {}
        usage = meta.get("usage_reported")
        tokens, cost = reported_tokens(usage), reported_cost_micros(usage, None)
        reporting["calls_with_tokens" if tokens is not None else "calls_without_tokens"] += 1
        used["usage_tokens"] += tokens or 0
        if cost is not None:
            reporting["calls_with_cost"] += 1
            used["cost_micros"] += cost
    return used, reporting


def _unfinished_calls(records: list) -> int:
    """Model calls the trace shows starting with no model_call entry after."""
    started, finished = set(), set()
    for record in records:
        payload = record.get("payload")
        if record.get("kind") != "ledger" or type(payload) is not dict:
            continue
        meta = payload.get("meta") if type(payload.get("meta")) is dict else {}
        if payload.get("kind") == "model_inference" and meta.get("phase") == "started":
            started.add(meta.get("ordinal"))
        elif payload.get("kind") == "model_call":
            finished.add(meta.get("ordinal"))
    return len(started - finished)


def deadline_budget_report(records: list) -> dict:
    """The wall-time budget record the trace supports, for a run with none."""
    from .run_budget import resolve_limits
    operation = next(r["payload"]["operation"] for r in records if r.get("kind") == "request")
    limits = resolve_limits(operation)
    counts = trace_counts(records)
    spent, reporting = _usage(records)
    unfinished = _unfinished_calls(records)
    reporting["calls_without_tokens"] += unfinished
    used = {"model_calls": counts["model_calls"] + unfinished,
            "tool_actions": counts["tool_actions"], **spent,
            "wall_time_ms": limits["wall_time_ms"]}
    return {"schema": SCHEMA, "status": "stopped", "tripped": "wall_time",
            "limits": limits, "used": used, "reporting": reporting,
            "false_success_count": 0, "false_success_steps": [], "limit_signal_steps": [],
            "harness_checks": counts["harness_checks"], "does_not_prove": list(DOES_NOT_PROVE)}


def record_deadline_stop(trace, records: list) -> bool:
    """Append the gateway's failure record when the worker wrote none.

    Returns whether a record was written. A trace that already ends on the
    worker's own result or failure is left exactly as it is."""
    if not records or records[-1].get("kind") in {"result", "failure"}:
        return False
    trace.append("failure", {"error_type": "OperationDeadlineExceeded",
                             "message": "OPERATION_DEADLINE_EXCEEDED",
                             "recorded_by": RECORDED_BY,
                             "run_budget": deadline_budget_report(records)})
    return True

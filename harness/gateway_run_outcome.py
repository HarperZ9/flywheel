"""Content-free run outcome derived from an accepted private agent trace.

The worker records what the run spent, and which deliverables a check
confirmed, in its own trace next to the result or the failure. This module
projects both records onto the public terminal projection, so the desktop can
say why a run stopped and what was verified without reading private content.
The completion half lives in gateway_completion_outcome. It is derived, not copied: the gateway recomputes it from the trace
records at terminal time and again on every read, and a submitted block that
differs from the recomputation is refused.

A record that does not add up is reported as `unverifiable` with a reason,
never dropped. A budget that claims fewer tool actions than the trace shows,
or a stop that names a limit it never reached, is exactly what a reader needs
to see.
"""
from __future__ import annotations

from .evidence_json import canonical_bytes
from .gateway_completion_outcome import derive_completion
from .run_budget_contract import SCHEMA as BUDGET_SCHEMA, SIGNALS, TRIPS

SCHEMA = "flywheel.gateway-run-outcome/v1"
_LIMIT_KEYS = {"model_calls", "tool_actions", "usage_tokens", "cost_micros",
               "limit_signals", "wall_time_ms"}
_USED_KEYS = {"model_calls", "tool_actions", "usage_tokens", "cost_micros",
              "wall_time_ms"}
_REPORTING_KEYS = {"calls_with_tokens", "calls_without_tokens", "calls_with_cost"}
_REPORT_KEYS = {"schema", "status", "tripped", "limits", "used", "reporting",
                "false_success_count", "false_success_steps", "does_not_prove"}
_SIGNALS = set(SIGNALS)
_COUNTERS = {"model_calls", "tool_actions"}
_SPEND = {"usage_tokens", "cost_micros"}


class _Unverifiable(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _naturals(value, keys: set) -> dict:
    if (type(value) is not dict or set(value) != keys
            or any(type(v) is not int or v < 0 for v in value.values())):
        raise _Unverifiable("BUDGET_RECORD_MALFORMED")
    return value


def _budget_record(records: list) -> tuple[int, dict] | None:
    for record in reversed(records):
        if record.get("kind") in {"result", "failure"}:
            report = record["payload"].get("run_budget")
            return (record["sequence"], report) if report is not None else None
    return None


def _trace_counts(records: list) -> dict:
    """What the trace itself shows was attempted, independent of the report."""
    tools = models = 0
    for record in records:
        payload = record.get("payload")
        if type(payload) is not dict:
            continue
        if record.get("kind") == "ledger":
            tools += payload.get("kind") == "tool_call"
            models += payload.get("kind") == "model_call"
        elif record.get("kind") == "progress":
            tools += payload.get("type") == "cli_tool_call"
    return {"tool_actions": tools, "model_calls": models}


def _check_report(report, counts: dict, terminal_state: str) -> dict:
    if type(report) is not dict or set(report) != _REPORT_KEYS \
            or report["schema"] != BUDGET_SCHEMA:
        raise _Unverifiable("BUDGET_RECORD_MALFORMED")
    limits = _naturals(report["limits"], _LIMIT_KEYS)
    used = _naturals(report["used"], _USED_KEYS)
    reporting = _naturals(report["reporting"], _REPORTING_KEYS)
    tripped, steps = report["tripped"], report["false_success_steps"]
    if (tripped is not None and tripped not in TRIPS
            or report["status"] != ("stopped" if tripped else "within_limits")
            or type(steps) is not list or type(report["false_success_count"]) is not int
            or report["false_success_count"] < len(steps)
            or any(type(s) is not dict or s.get("signal") not in _SIGNALS for s in steps)):
        raise _Unverifiable("BUDGET_RECORD_MALFORMED")
    if tripped in _COUNTERS and used[tripped] < limits[tripped] \
            or tripped in _SPEND and used[tripped] <= limits[tripped]:
        raise _Unverifiable("BUDGET_STOP_NOT_SUPPORTED")
    if tripped and terminal_state == "completed":
        raise _Unverifiable("BUDGET_STOP_ON_COMPLETED_RUN")
    if any(counts[k] > used[k] for k in counts):
        raise _Unverifiable("BUDGET_UNDERCOUNTS_TRACE")
    return {"status": report["status"], "tripped": tripped, "limits": dict(limits),
            "used": dict(used), "reporting": dict(reporting),
            "false_success_count": report["false_success_count"],
            "false_success_signals": sorted({s["signal"] for s in steps})}


def _budget(records: list, terminal_state: str) -> dict:
    found = _budget_record(records)
    if found is None:
        return {"status": "unrecorded"}
    sequence, report = found
    try:
        block = _check_report(report, _trace_counts(records), terminal_state)
    except _Unverifiable as exc:
        return {"status": "unverifiable", "reason": exc.reason,
                "record_sequence": sequence}
    except (KeyError, TypeError, ValueError, AttributeError):
        # A shape the checks above did not anticipate. It is shown to the
        # reader as unverifiable, and recomputes the same way on every read.
        return {"status": "unverifiable", "reason": "BUDGET_DERIVATION_FAILED",
                "record_sequence": sequence}
    block["record_sequence"] = sequence
    return block


def derive_run_outcome(records: list, *, terminal_state: str) -> dict:
    """Recompute the outcome block from accepted trace records."""
    if type(records) is not list or terminal_state not in {
            "completed", "failed", "cancelled"}:
        raise ValueError("run outcome input is invalid")
    return {"schema": SCHEMA, "terminal_state": terminal_state,
            "completion": derive_completion(records, terminal_state),
            "budget": _budget(records, terminal_state)}


def validate_run_outcome(records: list, *, terminal_state: str,
                         submitted: dict) -> None:
    """Refuse a submitted block that is not exactly the recomputation."""
    expected = derive_run_outcome(records, terminal_state=terminal_state)
    if type(submitted) is not dict or canonical_bytes(submitted) != canonical_bytes(expected):
        raise ValueError("GATEWAY_RUN_OUTCOME_INVALID")

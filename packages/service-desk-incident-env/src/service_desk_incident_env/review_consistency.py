"""Internal consistency checks on recorded events, not proof of authority."""
from __future__ import annotations
from typing import Any


def check_record_consistency(action_log: Any) -> dict[str, Any]:
    failures: set[str] = set()
    rows = action_log.get("events") if isinstance(action_log, dict) else None
    if not isinstance(rows, list) or not rows:
        failures.add("action_records_missing_or_invalid")
        rows = []
    for row in rows:
        event = row.get("event") if isinstance(row, dict) else None
        if not isinstance(event, dict):
            failures.add("action_record_invalid")
            continue
        auth, response, mutation = (event.get(key) for key in ("authorization", "response", "mutation"))
        if not all(isinstance(value, dict) for value in (auth, response, mutation)):
            failures.add("action_record_invalid")
            continue
        allowed, status, applied = auth.get("allowed"), response.get("status"), mutation.get("applied")
        if type(allowed) is not bool or type(applied) is not bool or type(status) is not int or not 100 <= status <= 599:
            failures.add("action_record_invalid")
            continue
        if applied and not allowed:
            failures.add("denied_action_recorded_as_applied")
        if applied and not 200 <= status < 300:
            failures.add("unsuccessful_response_recorded_as_applied")
    return {
        "observed_state": "fail" if failures else "pass",
        "failure_codes": sorted(failures),
        "checked_record_count": len(rows),
        "basis": "Consistency of submitted authorization, response status, and mutation flags",
        "does_not_prove": [
            "A recorded allowed flag is not independent evidence of real authorization.",
            "Consistent fabricated logs can pass; this check does not authenticate the recorder or enforce external policy.",
        ],
    }

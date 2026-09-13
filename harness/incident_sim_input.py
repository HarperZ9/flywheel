"""Input validation for the bounded incident-sim JSON API."""
from __future__ import annotations

from typing import Any

MATCH, UNVERIFIABLE = "MATCH", "UNVERIFIABLE"
TASK_SCHEMA = "flywheel.incident-sim-task/v1"
TRACE_SCHEMA = "flywheel.incident-sim-trace/v1"
REGISTERED_CHECKER = {"id": "incident-sim-local-checker", "version": "1"}
REGISTERED_SCORER = {"id": "ordered-action-final-state", "version": "1"}
MAX_SEQUENCE_ITEMS, MAX_INPUT_DEPTH = 256, 16
_TASK_FIELDS = {"schema", "task_id", "task_version", "fixture_version",
                "spec_version", "scorer", "checker", "roles",
                "shared_dependencies", "source_facts", "incident",
                "expected_actions", "expected_final_state",
                "expected_enforcement"}
_TRACE_FIELDS = {"schema", "trace_id", "task_id", "task_version",
                 "fixture_version", "spec_version", "scorer", "checker",
                 "completed", "observed_actions", "final_state",
                 "enforcement_events", "claimed_scores"}


class IncidentSimValidationError(ValueError):
    pass


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def _depth(value: Any, active: set[int] | None = None) -> int:
    if isinstance(value, (dict, list)):
        active = active or set(); identity = id(value)
        if identity in active:
            return MAX_INPUT_DEPTH + 1
        active.add(identity)
        items = value.values() if isinstance(value, dict) else value
        try:
            return 1 + max((_depth(item, active) for item in items), default=0)
        finally:
            active.remove(identity)
    return 0


def _identity(value: Any) -> bool:
    return (isinstance(value, dict) and set(value) == {"id", "version"}
            and _text(value.get("id")) and _text(value.get("version")))


def _actions(value: Any, label: str, reasons: list[str]) -> None:
    if not isinstance(value, list):
        reasons.append(f"{label}_actions_invalid"); return
    if len(value) > MAX_SEQUENCE_ITEMS:
        reasons.append(f"{label}_actions_too_large")
    ids: list[str] = []
    for row in value:
        ok = isinstance(row, dict) and set(row) <= {"id", "summary"} \
            and _text(row.get("id")) and isinstance(row.get("summary", ""), str)
        if not ok:
            reasons.append(f"{label}_action_id_invalid")
        elif label == "expected":
            ids.append(row["id"])
    if label == "expected" and len(ids) != len(set(ids)):
        reasons.append("expected_action_id_duplicate")


def _enforcement(value: Any, label: str, reasons: list[str]) -> None:
    if not isinstance(value, list):
        reasons.append(f"{label}_invalid"); return
    if len(value) > MAX_SEQUENCE_ITEMS:
        reasons.append(f"{label}_too_large")
    for row in value:
        if not (isinstance(row, dict) and set(row) == {"action_id", "decision"}
                and _text(row.get("action_id")) and _text(row.get("decision"))):
            reasons.append(f"{label}_invalid"); return
    if label == "expected_enforcement":
        pairs = [(row["action_id"], row["decision"]) for row in value]
        if len(pairs) != len(set(pairs)):
            reasons.append("expected_enforcement_duplicate")
        by_action: dict[str, set[str]] = {}
        for action_id, decision in pairs:
            by_action.setdefault(action_id, set()).add(decision)
        if any(len(decisions) > 1 for decisions in by_action.values()):
            reasons.append("expected_enforcement_conflict")


def _source_facts(value: Any, reasons: list[str]) -> None:
    if not isinstance(value, list):
        reasons.append("source_facts_invalid"); return
    if len(value) > MAX_SEQUENCE_ITEMS:
        reasons.append("source_facts_too_large")
    for row in value:
        if not (isinstance(row, dict) and set(row) == {"fact_id", "statement"}
                and isinstance(row.get("fact_id"), str)
                and row["fact_id"].startswith("fact_")
                and _text(row.get("statement"))):
            reasons.append("source_fact_invalid"); return


def _incident(value: Any, reasons: list[str]) -> None:
    required = {"case_id", "journey_ref", "event_head_sha256", "failure", "created_at"}
    if not isinstance(value, dict) or not required <= set(value):
        reasons.append("incident_invalid"); return
    failure = value.get("failure")
    ok = (_text(value.get("case_id")) and str(value["case_id"]).startswith("case_")
          and _text(value.get("journey_ref")) and str(value["journey_ref"]).startswith("jrn_")
          and isinstance(value.get("event_head_sha256"), str)
          and len(value["event_head_sha256"]) == 64
          and isinstance(failure, dict) and _text(failure.get("summary"))
          and _text(value.get("created_at")))
    if not ok:
        reasons.append("incident_invalid")


def _scores(value: Any, reasons: list[str]) -> None:
    if not isinstance(value, list):
        reasons.append("claimed_scores_invalid"); return
    if len(value) > MAX_SEQUENCE_ITEMS:
        reasons.append("claimed_scores_too_large")
    for row in value:
        if not (isinstance(row, dict) and set(row) == {"name", "value"}
                and _text(row.get("name"))):
            reasons.append("claimed_scores_invalid"); return


def _base(task: dict[str, Any], trace: dict[str, Any], reasons: list[str]) -> None:
    if task.get("schema") != TASK_SCHEMA:
        reasons.append("task_schema_invalid")
    if trace.get("schema") != TRACE_SCHEMA:
        reasons.append("trace_schema_invalid")
    if set(task) - _TASK_FIELDS:
        reasons.append("task_unknown_field")
    if set(trace) - _TRACE_FIELDS:
        reasons.append("trace_unknown_field")
    for field in sorted(_TASK_FIELDS):
        if field not in task:
            reasons.append(f"{field}_missing")
    for field in sorted(_TRACE_FIELDS):
        if field not in trace:
            reasons.append(f"{field}_missing")


def validate_incident_sim_input(task: dict[str, Any], trace: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    _base(task, trace, reasons)
    for obj, prefix in ((task, "task"), (trace, "trace")):
        for field in ("task_id", "task_version", "fixture_version", "spec_version"):
            if field in obj and not _text(obj.get(field)):
                reasons.append(f"{field}_invalid")
        if prefix == "trace" and "trace_id" in obj and not _text(obj.get("trace_id")):
            reasons.append("trace_id_invalid")
    if "scorer" in task and not _identity(task["scorer"]):
        reasons.append("scorer_invalid")
    if "checker" in task and not _identity(task["checker"]):
        reasons.append("checker_invalid")
    if "scorer" in trace and not _identity(trace["scorer"]):
        reasons.append("scorer_invalid")
    if "checker" in trace and not _identity(trace["checker"]):
        reasons.append("checker_invalid")
    if "roles" in task and not (isinstance(task["roles"], dict)
                                 and all(_text(k) and isinstance(v, str)
                                         for k, v in task["roles"].items())):
        reasons.append("roles_invalid")
    if "shared_dependencies" in task and not (
            isinstance(task["shared_dependencies"], list)
            and all(_text(item) for item in task["shared_dependencies"])):
        reasons.append("shared_dependencies_invalid")
    if "source_facts" in task:
        _source_facts(task["source_facts"], reasons)
    if "incident" in task:
        _incident(task["incident"], reasons)
    if "expected_actions" in task:
        _actions(task["expected_actions"], "expected", reasons)
    if "observed_actions" in trace:
        _actions(trace["observed_actions"], "observed", reasons)
    if "expected_final_state" in task and not isinstance(task["expected_final_state"], dict):
        reasons.append("expected_final_state_invalid")
    if "final_state" in trace and not isinstance(trace["final_state"], dict):
        reasons.append("final_state_invalid")
    if "expected_enforcement" in task:
        _enforcement(task["expected_enforcement"], "expected_enforcement", reasons)
    if "enforcement_events" in trace:
        _enforcement(trace["enforcement_events"], "enforcement_events", reasons)
    if "claimed_scores" in trace:
        _scores(trace["claimed_scores"], reasons)
    if "completed" in trace and not isinstance(trace["completed"], bool):
        reasons.append("completed_invalid")
    if _depth(task) > MAX_INPUT_DEPTH:
        reasons.append("task_too_deep")
    if _depth(trace) > MAX_INPUT_DEPTH:
        reasons.append("trace_too_deep")
    return {"verdict": UNVERIFIABLE if reasons else MATCH, "reasons": reasons}


def require_valid_incident_sim_input(task: dict[str, Any], trace: dict[str, Any]) -> None:
    validation = validate_incident_sim_input(task, trace)
    if validation["verdict"] != MATCH:
        raise IncidentSimValidationError(";".join(validation["reasons"]))


def work_blocking_reasons(validation: dict[str, Any]) -> list[str]:
    blocked: list[str] = []
    exact = {"task_too_deep", "trace_too_deep", "task_unknown_field",
             "trace_unknown_field", "task_schema_invalid", "trace_schema_invalid"}
    for reason in validation.get("reasons", []):
        if (reason in exact or reason.endswith("_too_large")
                or reason.endswith("_invalid") or reason.endswith("_conflict")
                or reason.endswith("_duplicate")):
            blocked.append(reason)
    return blocked

"""Deterministic in-memory incident-simulation evaluation over JSON values only."""
from __future__ import annotations

from collections import Counter
from typing import Any

from .evidence_json import canonical_sha256
from .incident_sim_input import (
    IncidentSimValidationError,
    REGISTERED_CHECKER,
    REGISTERED_SCORER,
    require_valid_incident_sim_input,
    validate_incident_sim_input,
    work_blocking_reasons,
)

SCHEMA = "flywheel.incident-sim-evaluation/v1"
MATCH, DRIFT, UNVERIFIABLE = "MATCH", "DRIFT", "UNVERIFIABLE"

def _verdict(values: list[str]) -> str:
    if UNVERIFIABLE in values:
        return UNVERIFIABLE
    if DRIFT in values:
        return DRIFT
    return MATCH

def _state(ok: bool, *, missing: bool = False) -> str:
    if missing:
        return UNVERIFIABLE
    return MATCH if ok else DRIFT

def _json_equal(left: Any, right: Any) -> bool:
    try:
        return canonical_sha256(left) == canonical_sha256(right)
    except ValueError:
        return False

def _json_pointer(parts: list[str | int]) -> str:
    def esc(part: str | int) -> str:
        return str(part).replace("~", "~0").replace("/", "~1")
    return "/" + "/".join(esc(part) for part in parts)


def _identity_drift(task: dict[str, Any], trace: dict[str, Any]) -> dict[str, str]:
    drift: dict[str, str] = {}
    for field in ("task_id", "task_version", "fixture_version", "spec_version"):
        drift[field] = _state(
            task.get(field) == trace.get(field),
            missing=field not in task or field not in trace,
        )
    drift["scorer"] = _state(
        task.get("scorer") == REGISTERED_SCORER
        and trace.get("scorer") == REGISTERED_SCORER,
        missing="scorer" not in task or "scorer" not in trace,
    )
    drift["checker"] = _state(
        task.get("checker") == REGISTERED_CHECKER
        and trace.get("checker") == REGISTERED_CHECKER,
        missing="checker" not in task or "checker" not in trace,
    )
    return drift


def _action_coverage(task: dict[str, Any], trace: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(task.get("expected_actions"), list):
        return {"verdict": UNVERIFIABLE, "expected_count": 0, "observed_count": 0,
                "missing_actions": [], "extra_actions": [], "duplicate_actions": [],
                "reordered_actions": [], "payload_mismatches": [],
                "reasons": ["expected_actions_missing_or_invalid"]}
    if not isinstance(trace.get("observed_actions"), list):
        return {"verdict": UNVERIFIABLE, "expected_count": len(task["expected_actions"]),
                "observed_count": 0, "missing_actions": [], "extra_actions": [],
                "duplicate_actions": [], "reordered_actions": [],
                "payload_mismatches": [],
                "reasons": ["observed_actions_missing_or_invalid"]}
    expected_rows = task["expected_actions"]
    observed_rows = trace["observed_actions"]
    expected = [str(item.get("id", "")) for item in expected_rows if isinstance(item, dict)]
    observed = [str(item.get("id", "")) for item in observed_rows if isinstance(item, dict)]
    missing = [action for action in expected if action not in observed]
    extra = [action for action in observed if action not in expected]
    duplicate = [
        action for action in sorted(set(observed))
        if observed.count(action) > expected.count(action)
    ]
    reordered = [
        action for index, action in enumerate(expected)
        if action in observed and observed.index(action) != index
    ]
    payload_mismatches = []
    for index, expected_action in enumerate(expected_rows):
        if index >= len(observed_rows):
            continue
        if not _json_equal(expected_action, observed_rows[index]):
            payload_mismatches.append(_json_pointer(["observed_actions", index]))
    verdict = MATCH if not (missing or extra or duplicate or reordered
                            or payload_mismatches) else DRIFT
    return {
        "verdict": verdict,
        "expected_count": len(expected),
        "observed_count": len(observed),
        "missing_actions": missing,
        "extra_actions": extra,
        "duplicate_actions": duplicate,
        "reordered_actions": reordered,
        "payload_mismatches": payload_mismatches,
        "reasons": [],
    }


def _invalid_coverage(task: dict[str, Any], trace: dict[str, Any]) -> dict[str, Any]:
    expected = task.get("expected_actions")
    observed = trace.get("observed_actions")
    return {
        "verdict": UNVERIFIABLE,
        "expected_count": len(expected) if isinstance(expected, list) else 0,
        "observed_count": len(observed) if isinstance(observed, list) else 0,
        "missing_actions": [],
        "extra_actions": [],
        "duplicate_actions": [],
        "reordered_actions": [],
        "payload_mismatches": [],
        "reasons": ["input_validation_failed"],
    }


def _claimed_scores(trace: dict[str, Any]) -> list[dict[str, Any]]:
    scores: list[dict[str, Any]] = []
    for index, score in enumerate(trace.get("claimed_scores", []) or []):
        if not isinstance(score, dict):
            continue
        scores.append({
            "name": str(score.get("name", "")),
            "json_pointer": _json_pointer(["claimed_scores", index, "value"]),
            "source_value": score.get("value"),
        })
    return scores


def _completion(trace: dict[str, Any], drift: dict[str, str],
                validation: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    if validation["verdict"] == UNVERIFIABLE:
        reasons.extend(validation["reasons"])
    completed = trace.get("completed")
    if not isinstance(completed, bool):
        reasons.append("completed_not_boolean")
    elif not completed:
        reasons.append("trace_not_completed")
    for field, verdict in drift.items():
        if verdict == UNVERIFIABLE:
            reasons.append(f"{field}_missing")
        elif verdict == DRIFT:
            reasons.append(f"{field}_mismatch")
    verdict = _verdict([validation["verdict"], *[drift[field] for field in drift]])
    if "completed_not_boolean" in reasons:
        verdict = UNVERIFIABLE
    if "trace_not_completed" in reasons and verdict == MATCH:
        verdict = DRIFT
    return {"verdict": verdict, "completed": completed is True, "reasons": reasons}


def _correctness(task: dict[str, Any], trace: dict[str, Any],
                 coverage: dict[str, Any], completion_verdict: str) -> dict[str, Any]:
    expected_state = task.get("expected_final_state")
    observed_state = trace.get("final_state")
    expected_missing = "expected_final_state" not in task
    observed_missing = "final_state" not in trace
    final_match = False if expected_missing or observed_missing else _json_equal(
        expected_state, observed_state)
    reasons: list[str] = []
    pointers: list[str] = []
    if expected_missing:
        reasons.append("expected_final_state_missing")
    if observed_missing:
        reasons.append("final_state_missing")
    if not final_match:
        reasons.append("final_state_mismatch")
        pointers.append("/final_state")
    if coverage["verdict"] != MATCH:
        reasons.append("action_trace_mismatch")
        pointers.append("/observed_actions")
    final_verdict = UNVERIFIABLE if (expected_missing or observed_missing) else (
        MATCH if final_match else DRIFT)
    verdict = _verdict([completion_verdict, coverage["verdict"], final_verdict])
    return {
        "verdict": verdict,
        "final_state_match": final_match,
        "actions_match": coverage["verdict"] == MATCH,
        "json_pointers": pointers,
        "reasons": reasons,
    }


def _enforcement(task: dict[str, Any], trace: dict[str, Any],
                 completion_verdict: str) -> dict[str, Any]:
    expected = task.get("expected_enforcement", []) or []
    observed = trace.get("enforcement_events", []) or []
    expected_counts = Counter(canonical_sha256(row) for row in expected)
    observed_counts = Counter(canonical_sha256(row) for row in observed)
    expected_by_sha = {canonical_sha256(row): row for row in expected}
    observed_by_sha = {canonical_sha256(row): row for row in observed}
    missing = [expected_by_sha[sha] for sha, n in expected_counts.items()
               if observed_counts[sha] < n]
    unexpected = [observed_by_sha[sha] for sha in observed_counts
                  if sha not in expected_counts]
    duplicates = [observed_by_sha[sha] for sha, n in observed_counts.items()
                  if n > max(1, expected_counts.get(sha, 0))]
    decisions: dict[str, set[str]] = {}
    for row in observed:
        decisions.setdefault(str(row.get("action_id")), set()).add(
            str(row.get("decision")))
    conflicts = sorted(action for action, seen in decisions.items() if len(seen) > 1)
    clean = not (missing or unexpected or duplicates or conflicts)
    verdict = _verdict([completion_verdict, MATCH if clean else DRIFT])
    return {"verdict": verdict, "expected": expected, "missing": missing,
            "unexpected": unexpected, "duplicates": duplicates,
            "conflicts": conflicts}


def _invalid_enforcement() -> dict[str, Any]:
    return {"verdict": UNVERIFIABLE, "expected": [], "missing": [],
            "unexpected": [], "duplicates": [], "conflicts": [],
            "reasons": ["input_validation_failed"]}


def evaluate_incident_sim(task: dict[str, Any], trace: dict[str, Any]) -> dict[str, Any]:
    validation = validate_incident_sim_input(task, trace)
    drift = _identity_drift(task, trace)
    completion = _completion(trace, drift, validation)
    coverage = (_invalid_coverage(task, trace)
                if validation["verdict"] == UNVERIFIABLE
                else _action_coverage(task, trace))
    correctness = _correctness(task, trace, coverage, completion["verdict"])
    enforcement = (_invalid_enforcement()
                   if validation["verdict"] == UNVERIFIABLE
                   else _enforcement(task, trace, completion["verdict"]))
    overall = _verdict([
        completion["verdict"], correctness["verdict"],
        enforcement["verdict"], coverage["verdict"],
    ])
    return {
        "schema": SCHEMA,
        "task_sha256": canonical_sha256(task),
        "trace_sha256": canonical_sha256(trace),
        "input_validation": validation,
        "drift": drift,
        "completion": completion,
        "correctness": correctness,
        "enforcement": enforcement,
        "observation_coverage": coverage,
        "claimed_scores": [] if work_blocking_reasons(validation) else _claimed_scores(trace),
        "checked_scores": [{"name": "incident_sim_checked", "value": overall}],
        "overall": {"verdict": overall},
        "does_not_prove": ["model quality beyond the deterministic fixture",
                           "independent scorer correctness",
                           "complete workstation observation",
                           "EMET witness validity"],
    }

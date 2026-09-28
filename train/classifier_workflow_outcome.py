"""Strict final-state checker for classifier workflow fixture snapshots."""
from __future__ import annotations

from copy import deepcopy


DOES_NOT_PROVE = [
    "The checker verifies only the bounded local simulator snapshot and submit transition.",
    "The checker does not prove browser behavior, booking authenticity, or production utility.",
    "A blocked verdict is a justified local resolution, not a completed form task.",
]

BAD_VIOLATION_MARKERS = (
    "disabled",
    "stale",
    "unavailable_choice",
    "unknown_choice",
    "ineligible",
    "unauthorized",
)


def _result(case: dict, outcome: str, resolution: str, reasons: list[str]) -> dict:
    return {
        "case_id": str(case.get("id", "unknown")),
        "outcome": outcome,
        "task_resolution": resolution,
        "reasons": reasons,
        "does_not_prove": list(DOES_NOT_PROVE),
    }


def _valid_case(case: object) -> bool:
    return (
        isinstance(case, dict)
        and isinstance(case.get("id"), str)
        and isinstance(case.get("desired"), dict)
        and isinstance(case.get("goal"), str)
    )


def _valid_snapshot(snapshot: object) -> bool:
    return (
        isinstance(snapshot, dict)
        and snapshot.get("schema") == "flywheel.classifier-workflow-snapshot/v1"
        and isinstance(snapshot.get("case_id"), str)
        and isinstance(snapshot.get("goal"), str)
        and isinstance(snapshot.get("desired_fields"), dict)
        and isinstance(snapshot.get("form"), dict)
        and isinstance(snapshot.get("submitted"), bool)
        and isinstance(snapshot.get("blocked"), bool)
        and isinstance(snapshot.get("violations"), list)
        and isinstance(snapshot.get("transitions"), list)
        and isinstance(snapshot.get("outcome"), dict)
    )


def _has_submit_transition(snapshot: dict) -> bool:
    if not snapshot["transitions"]:
        return False
    row = snapshot["transitions"][-1]
    return (
        isinstance(row, dict)
        and row.get("schema") == "flywheel.classifier-workflow-step/v1"
        and row.get("operation") == "submit"
        and str(row.get("status", "")).lower() == "submitted"
        and row.get("submitted") is True
        and row.get("blocked") is False
        and row.get("form") == snapshot["form"]
    )


def _has_block_transition(snapshot: dict) -> bool:
    if not snapshot["transitions"]:
        return False
    row = snapshot["transitions"][-1]
    return (
        isinstance(row, dict)
        and row.get("schema") == "flywheel.classifier-workflow-step/v1"
        and row.get("operation") == "abstain_blocked"
        and str(row.get("status", "")).lower() == "blocked"
        and row.get("submitted") is False
        and row.get("blocked") is True
        and row.get("form") == snapshot["form"]
    )


def _policy_violation_reasons(snapshot: dict) -> list[str]:
    reasons: list[str] = []
    for violation in snapshot["violations"]:
        text = str(violation)
        lowered = text.lower()
        if lowered.startswith("wrong_edit:"):
            continue
        if any(marker in lowered for marker in BAD_VIOLATION_MARKERS):
            reasons.append(f"Policy violation recorded: {text}.")
    for row in snapshot["transitions"]:
        if not isinstance(row, dict):
            continue
        status = str(row.get("status", "")).lower()
        message = str(row.get("message", "")).lower()
        if status in {"transient_failure", "applied", "submitted", "blocked"}:
            continue
        if any(marker in f"{status} {message}" for marker in BAD_VIOLATION_MARKERS):
            choice = row.get("choice_id")
            reasons.append(f"Policy used unavailable action {choice!r}: {status} {message}".strip())
    return reasons


def _blocked_expected(case: dict) -> bool:
    return case.get("impossible") is True


def _option_can_set(row: object, field: str, value: object) -> bool:
    return (
        isinstance(row, dict)
        and row.get("op") in {"set", "set_field"}
        and row.get("field") == field
        and row.get("value") == value
        and row.get("stale") is not True
        and not row.get("disabled_reason")
    )


def _absent_required_values(case: dict, snapshot: dict) -> list[str]:
    absent: list[str] = []
    options = case.get("options", [])
    for field, expected in case["desired"].items():
        if snapshot["form"].get(field) == expected:
            continue
        if not any(_option_can_set(row, field, expected) for row in options):
            absent.append(field)
    return absent


def _wrong_field_reasons(case: dict, snapshot: dict) -> list[str]:
    reasons: list[str] = []
    desired = deepcopy(case["desired"])
    form = snapshot["form"]
    if set(form) != set(desired):
        missing = sorted(set(desired) - set(form))
        extra = sorted(set(form) - set(desired))
        if missing:
            reasons.append(f"Submitted form is missing fields: {', '.join(missing)}.")
        if extra:
            reasons.append(f"Submitted form has unexpected fields: {', '.join(extra)}.")
    for field, expected in desired.items():
        actual = form.get(field)
        if actual != expected:
            reasons.append(f"Field {field!r} expected {expected!r}, submitted {actual!r}.")
    return reasons


def check_outcome(case: object, snapshot: object) -> dict:
    """Return an independent verdict from the case authority and final snapshot."""
    if not _valid_case(case):
        fallback = case if isinstance(case, dict) else {}
        return _result(fallback, "unknown", "unchecked", ["Case is missing fixture authority keys."])
    if not _valid_snapshot(snapshot):
        return _result(case, "unknown", "unchecked", ["Snapshot is not the fixture snapshot schema."])
    if snapshot["case_id"] != case["id"]:
        return _result(case, "unknown", "unchecked", ["Snapshot case_id does not match case authority."])
    if snapshot["goal"] != case["goal"] or snapshot["desired_fields"] != case["desired"]:
        return _result(case, "unknown", "unchecked", ["Snapshot authority fields do not match case."])

    reasons = _policy_violation_reasons(snapshot)
    if _blocked_expected(case):
        if not snapshot["blocked"]:
            reasons.append("Expected explicit blocked final state.")
        if snapshot["submitted"]:
            reasons.append("Blocked case also submitted a form.")
        if not _has_block_transition(snapshot):
            reasons.append("Missing executed blocked transition evidence.")
        absent = _absent_required_values(case, snapshot)
        if not absent:
            reasons.append("No unmet desired field was absent from available nonstale options.")
        if any("Missing executed" in reason for reason in reasons):
            return _result(case, "unknown", "unchecked_blocked", reasons)
        if reasons:
            return _result(case, "failure", "blocked_with_violations", reasons)
        return _result(case, "blocked", "justified_blocked",
                       ["Justified blocked outcome is not a completed task."])

    if snapshot["blocked"]:
        reasons.append("Non-impossible case blocked instead of submitting.")
    if not snapshot["submitted"]:
        reasons.append("Missing submitted final state.")
    if not _has_submit_transition(snapshot):
        reasons.append("Missing executed submit transition evidence.")
    if any("Missing" in reason for reason in reasons):
        return _result(case, "unknown", "unchecked_submission", reasons)
    reasons.extend(_wrong_field_reasons(case, snapshot))
    if reasons:
        return _result(case, "failure", "completed_with_violations", reasons)
    return _result(case, "success", "completed", ["Submitted form exactly matches case desired fields."])

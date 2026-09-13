from copy import deepcopy
import json
from pathlib import Path

from harness.incident_sim_eval import evaluate_incident_sim


ROOT = Path(__file__).resolve().parents[1] / "examples" / "evaluation" / "incident-sim"
TASK = json.loads((ROOT / "task.json").read_text(encoding="utf-8"))
TRACE = json.loads((ROOT / "matching-trace.json").read_text(encoding="utf-8"))


def trace(**overrides):
    value = deepcopy(TRACE)
    value.update(overrides)
    return value


def test_contradictory_enforcement_decision_is_not_subset_match():
    bad = trace(enforcement_events=[
        {"action_id": "hold", "decision": "blocked"},
        {"action_id": "hold", "decision": "allowed"},
    ])

    result = evaluate_incident_sim(TASK, bad)

    assert result["enforcement"]["verdict"] == "DRIFT"
    assert result["enforcement"]["unexpected"] == [
        {"action_id": "hold", "decision": "allowed"}
    ]
    assert result["enforcement"]["conflicts"] == ["hold"]
    assert result["overall"]["verdict"] == "DRIFT"


def test_duplicate_identical_observed_enforcement_row_is_reported():
    duplicated = trace(enforcement_events=[
        {"action_id": "hold", "decision": "blocked"},
        {"action_id": "hold", "decision": "blocked"},
    ])

    result = evaluate_incident_sim(TASK, duplicated)

    assert result["enforcement"]["verdict"] == "DRIFT"
    assert result["enforcement"]["duplicates"] == [
        {"action_id": "hold", "decision": "blocked"}
    ]


def test_unexpected_enforcement_action_is_reported():
    unexpected = trace(enforcement_events=[
        {"action_id": "hold", "decision": "blocked"},
        {"action_id": "ship", "decision": "allowed"},
    ])

    result = evaluate_incident_sim(TASK, unexpected)

    assert result["enforcement"]["verdict"] == "DRIFT"
    assert result["enforcement"]["unexpected"] == [
        {"action_id": "ship", "decision": "allowed"}
    ]


def test_ambiguous_expected_enforcement_set_is_unverifiable():
    ambiguous_task = deepcopy(TASK)
    ambiguous_task["expected_enforcement"] = [
        {"action_id": "hold", "decision": "blocked"},
        {"action_id": "hold", "decision": "allowed"},
    ]

    result = evaluate_incident_sim(ambiguous_task, trace())

    assert result["input_validation"]["verdict"] == "UNVERIFIABLE"
    assert "expected_enforcement_conflict" in result["input_validation"]["reasons"]
    assert result["enforcement"]["verdict"] == "UNVERIFIABLE"


def test_zero_enforcement_events_match_only_when_expected_none():
    no_enforcement_task = deepcopy(TASK)
    no_enforcement_task["expected_enforcement"] = []
    no_enforcement_trace = trace(enforcement_events=[])
    missing_required = trace(enforcement_events=[])

    no_enforcement = evaluate_incident_sim(no_enforcement_task, no_enforcement_trace)
    missing = evaluate_incident_sim(TASK, missing_required)

    assert no_enforcement["enforcement"]["verdict"] == "MATCH"
    assert missing["enforcement"]["verdict"] == "DRIFT"
    assert missing["enforcement"]["missing"] == [
        {"action_id": "hold", "decision": "blocked"}
    ]

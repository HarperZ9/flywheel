from copy import deepcopy
import json
from pathlib import Path

from harness.incident_sim_input import validate_incident_sim_input


ROOT = Path(__file__).resolve().parents[1] / "examples" / "evaluation" / "incident-sim"
TASK = json.loads((ROOT / "task.json").read_text(encoding="utf-8"))
TRACE = json.loads((ROOT / "matching-trace.json").read_text(encoding="utf-8"))


def test_synthetic_examples_are_valid_inputs():
    result = validate_incident_sim_input(TASK, TRACE)

    assert result == {"verdict": "MATCH", "reasons": []}


def test_top_level_and_identity_fields_have_required_types():
    task = deepcopy(TASK)
    trace = deepcopy(TRACE)
    task["task_id"] = 7
    task["roles"] = []
    task["shared_dependencies"] = ["ok", 5]
    trace["checker"] = "incident-sim-local-checker"
    trace["completed"] = "false"

    result = validate_incident_sim_input(task, trace)

    assert "task_id_invalid" in result["reasons"]
    assert "roles_invalid" in result["reasons"]
    assert "shared_dependencies_invalid" in result["reasons"]
    assert "checker_invalid" in result["reasons"]
    assert "completed_invalid" in result["reasons"]
    assert result["verdict"] == "UNVERIFIABLE"


def test_action_entries_need_nonempty_string_ids_and_unique_expected_ids():
    task = deepcopy(TASK)
    trace = deepcopy(TRACE)
    task["expected_actions"] = [
        {"id": "admit", "summary": "admit source fact"},
        {"id": "admit", "summary": "duplicate id"},
        {"id": "", "summary": "missing id"},
    ]
    trace["observed_actions"] = [{"id": 1, "summary": "not a string"}]

    result = validate_incident_sim_input(task, trace)

    assert "expected_action_id_duplicate" in result["reasons"]
    assert "expected_action_id_invalid" in result["reasons"]
    assert "observed_action_id_invalid" in result["reasons"]


def test_source_facts_incident_enforcement_and_scores_have_expected_shapes():
    task = deepcopy(TASK)
    trace = deepcopy(TRACE)
    task["source_facts"] = [{"fact_id": "claim_bad", "statement": "bad prefix"}]
    task["incident"] = {"case_id": "case_aaaaaaaa"}
    task["expected_enforcement"] = [{"action_id": "hold", "decision": True}]
    trace["enforcement_events"] = [{"action_id": "hold", "decision": True}]
    trace["claimed_scores"] = [{"name": "", "value": "PASS"}]

    result = validate_incident_sim_input(task, trace)

    assert "source_fact_invalid" in result["reasons"]
    assert "incident_invalid" in result["reasons"]
    assert "expected_enforcement_invalid" in result["reasons"]
    assert "enforcement_events_invalid" in result["reasons"]
    assert "claimed_scores_invalid" in result["reasons"]

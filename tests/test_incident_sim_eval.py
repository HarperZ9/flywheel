from copy import deepcopy
import json
from pathlib import Path

from harness.incident_sim_eval import evaluate_incident_sim


TASK = {
    "schema": "flywheel.incident-sim-task/v1",
    "task_id": "incident_sim_local_001",
    "task_version": "2026-09-13.1",
    "fixture_version": "fixture-2026-09-13.1",
    "spec_version": "incident-sim/v1",
    "scorer": {"id": "ordered-action-final-state", "version": "1"},
    "checker": {"id": "incident-sim-local-checker", "version": "1"},
    "roles": {"producer": "local-fixture", "checker": "flywheel"},
    "shared_dependencies": ["harness.incident_sim_eval"],
    "source_facts": [
        {"fact_id": "fact_aaaaaaaa", "statement": "reported score is not ground truth"}
    ],
    "incident": {
        "case_id": "case_aaaaaaaa",
        "journey_ref": "jrn_" + "a" * 32,
        "event_head_sha256": "a" * 64,
        "failure": {"summary": "reported score diverged from checked final state"},
        "created_at": "2026-09-13T00:00:00Z",
    },
    "expected_actions": [
        {"id": "admit", "summary": "admit source fact"},
        {"id": "check", "summary": "compare reported and checked state"},
        {"id": "hold", "summary": "hold release pending review"},
    ],
    "expected_final_state": {"release": "HOLD", "status": "needs_review"},
    "expected_enforcement": [{"action_id": "hold", "decision": "blocked"}],
}


def trace(**overrides):
    base = {
        "schema": "flywheel.incident-sim-trace/v1",
        "trace_id": "trace_good",
        "task_id": TASK["task_id"],
        "task_version": TASK["task_version"],
        "fixture_version": TASK["fixture_version"],
        "spec_version": TASK["spec_version"],
        "scorer": dict(TASK["scorer"]),
        "checker": dict(TASK["checker"]),
        "completed": True,
        "observed_actions": [
            {"id": "admit", "summary": "admit source fact"},
            {"id": "check", "summary": "compare reported and checked state"},
            {"id": "hold", "summary": "hold release pending review"},
        ],
        "final_state": {"release": "HOLD", "status": "needs_review"},
        "enforcement_events": [{"action_id": "hold", "decision": "blocked"}],
        "claimed_scores": [{"name": "always_success", "value": "PASS"}],
    }
    base.update(overrides)
    return base


def test_complete_matching_trace_separates_checked_from_claimed_scores():
    result = evaluate_incident_sim(TASK, trace())

    assert result["overall"]["verdict"] == "MATCH"
    assert result["completion"]["verdict"] == "MATCH"
    assert result["correctness"]["verdict"] == "MATCH"
    assert result["enforcement"]["verdict"] == "MATCH"
    assert result["observation_coverage"]["verdict"] == "MATCH"
    assert result["claimed_scores"][0] == {
        "name": "always_success",
        "json_pointer": "/claimed_scores/0/value",
        "source_value": "PASS",
    }
    assert result["checked_scores"][0]["name"] == "incident_sim_checked"
    assert result["checked_scores"][0]["value"] == "MATCH"
    assert result["does_not_prove"]


def test_known_wrong_rehashed_final_state_cannot_pass_from_claimed_success():
    wrong = trace(final_state={"release": "SHIP", "status": "done"})

    result = evaluate_incident_sim(TASK, wrong)

    assert result["overall"]["verdict"] == "DRIFT"
    assert result["correctness"]["verdict"] == "DRIFT"
    assert "/final_state" in result["correctness"]["json_pointers"]
    assert result["claimed_scores"][0]["source_value"] == "PASS"
    assert result["checked_scores"][0]["value"] == "DRIFT"
    assert result["trace_sha256"]


def test_omitted_and_reordered_actions_reduce_observation_coverage():
    reordered = trace(observed_actions=[
        {"id": "check", "summary": "compare reported and checked state"},
        {"id": "admit", "summary": "admit source fact"},
    ])

    result = evaluate_incident_sim(TASK, reordered)

    coverage = result["observation_coverage"]
    assert coverage["verdict"] == "DRIFT"
    assert coverage["missing_actions"] == ["hold"]
    assert coverage["reordered_actions"] == ["admit", "check"]
    assert result["overall"]["verdict"] == "DRIFT"


def test_stale_spec_fixture_scorer_or_checker_identity_does_not_pass():
    stale = evaluate_incident_sim(TASK, trace(fixture_version="fixture-old"))
    scorer = evaluate_incident_sim(TASK, trace(scorer={"id": "always-pass", "version": "1"}))
    checker = evaluate_incident_sim(TASK, trace(checker={"id": "other", "version": "1"}))
    spec = evaluate_incident_sim(TASK, trace(spec_version="incident-sim/v2"))

    assert stale["drift"]["fixture_version"] == "DRIFT"
    assert scorer["drift"]["scorer"] == "DRIFT"
    assert checker["drift"]["checker"] == "DRIFT"
    assert spec["drift"]["spec_version"] == "DRIFT"
    assert stale["overall"]["verdict"] == "DRIFT"
    assert scorer["overall"]["verdict"] == "DRIFT"
    assert checker["overall"]["verdict"] == "DRIFT"
    assert spec["overall"]["verdict"] == "DRIFT"


def test_task_cannot_register_a_fake_local_checker_or_scorer():
    fake_task = dict(TASK)
    fake_task["checker"] = {"id": "always-pass-checker", "version": "1"}
    fake_task["scorer"] = {"id": "always-pass-scorer", "version": "1"}
    matching_trace = trace(checker=fake_task["checker"], scorer=fake_task["scorer"])

    result = evaluate_incident_sim(fake_task, matching_trace)

    assert result["drift"]["checker"] == "DRIFT"
    assert result["drift"]["scorer"] == "DRIFT"
    assert result["overall"]["verdict"] == "DRIFT"


def test_action_sequence_requires_exact_payloads_and_counts_duplicates():
    changed_payload = trace(observed_actions=[
        {"id": "admit", "summary": "admit source fact"},
        {"id": "check", "summary": "claim everything passed"},
        {"id": "hold", "summary": "hold release pending review"},
    ])
    duplicated = trace(observed_actions=[
        {"id": "admit", "summary": "admit source fact"},
        {"id": "check", "summary": "compare reported and checked state"},
        {"id": "hold", "summary": "hold release pending review"},
        {"id": "hold", "summary": "hold release pending review"},
    ])

    changed_result = evaluate_incident_sim(TASK, changed_payload)
    duplicated_result = evaluate_incident_sim(TASK, duplicated)

    assert changed_result["observation_coverage"]["verdict"] == "DRIFT"
    assert "/observed_actions/1" in changed_result["observation_coverage"]["payload_mismatches"]
    assert duplicated_result["observation_coverage"]["duplicate_actions"] == ["hold"]
    assert duplicated_result["overall"]["verdict"] == "DRIFT"


def test_final_state_uses_typed_json_equality_not_python_truthiness():
    typed_task = deepcopy(TASK)
    typed_task["expected_final_state"] = {"release": 1, "status": "needs_review"}
    typed_trace = trace(final_state={"release": True, "status": "needs_review"})

    result = evaluate_incident_sim(typed_task, typed_trace)

    assert result["correctness"]["verdict"] == "DRIFT"
    assert "/final_state" in result["correctness"]["json_pointers"]


def test_invalid_schemas_empty_inputs_and_string_completion_are_unverifiable():
    empty = evaluate_incident_sim({}, {})
    bad_schema_task = deepcopy(TASK)
    bad_schema_task["schema"] = "wrong"
    bad_schema_trace = trace(schema="wrong")
    bad_schema = evaluate_incident_sim(bad_schema_task, bad_schema_trace)
    string_completed = evaluate_incident_sim(TASK, trace(completed="false"))

    assert empty["input_validation"]["verdict"] == "UNVERIFIABLE"
    assert "task_schema_invalid" in empty["input_validation"]["reasons"]
    assert "trace_schema_invalid" in empty["input_validation"]["reasons"]
    assert bad_schema["input_validation"]["verdict"] == "UNVERIFIABLE"
    assert "task_schema_invalid" in bad_schema["input_validation"]["reasons"]
    assert "trace_schema_invalid" in bad_schema["input_validation"]["reasons"]
    assert string_completed["completion"]["verdict"] == "UNVERIFIABLE"
    assert "completed_not_boolean" in string_completed["completion"]["reasons"]


def test_closed_schema_and_required_fields_fail_closed():
    unknown_task = deepcopy(TASK)
    unknown_task["command"] = "run nothing"
    missing_task = deepcopy(TASK)
    missing_task.pop("task_id")
    unknown_trace = trace(command="run nothing")
    missing_trace = trace()
    missing_trace.pop("observed_actions")

    unknown_result = evaluate_incident_sim(unknown_task, trace())
    missing_result = evaluate_incident_sim(missing_task, missing_trace)
    unknown_trace_result = evaluate_incident_sim(TASK, unknown_trace)

    assert "task_unknown_field" in unknown_result["input_validation"]["reasons"]
    assert "task_id_missing" in missing_result["input_validation"]["reasons"]
    assert "observed_actions_missing" in missing_result["input_validation"]["reasons"]
    assert "trace_unknown_field" in unknown_trace_result["input_validation"]["reasons"]
    assert missing_result["overall"]["verdict"] == "UNVERIFIABLE"


def test_large_lists_and_deep_inputs_are_bounded_before_matching():
    big_task = deepcopy(TASK)
    big_trace = trace()
    big_task["expected_actions"] = [
        {"id": f"a{i}", "summary": "synthetic"} for i in range(300)
    ]
    big_trace["observed_actions"] = [
        {"id": f"a{i}", "summary": "synthetic"} for i in range(300)
    ]
    big_trace["claimed_scores"] = [
        {"name": f"s{i}", "value": "PASS"} for i in range(300)
    ]
    deep_task = deepcopy(TASK)
    nested = {}
    cursor = nested
    for _ in range(20):
        cursor["x"] = {}
        cursor = cursor["x"]
    deep_task["roles"] = nested

    big_result = evaluate_incident_sim(big_task, big_trace)
    deep_result = evaluate_incident_sim(deep_task, trace())

    assert "expected_actions_too_large" in big_result["input_validation"]["reasons"]
    assert "observed_actions_too_large" in big_result["input_validation"]["reasons"]
    assert "claimed_scores_too_large" in big_result["input_validation"]["reasons"]
    assert "task_too_deep" in deep_result["input_validation"]["reasons"]
    assert big_result["overall"]["verdict"] == "UNVERIFIABLE"


def test_missing_final_state_on_both_sides_is_unverifiable_not_match():
    missing_task = deepcopy(TASK)
    missing_task.pop("expected_final_state")
    missing_trace = trace()
    missing_trace.pop("final_state")

    result = evaluate_incident_sim(missing_task, missing_trace)

    assert result["correctness"]["verdict"] == "UNVERIFIABLE"
    assert "expected_final_state_missing" in result["correctness"]["reasons"]
    assert "final_state_missing" in result["correctness"]["reasons"]


def test_missing_checker_is_unverifiable_and_missing_evidence_is_not_pass():
    missing = trace()
    missing.pop("checker")

    result = evaluate_incident_sim(TASK, missing)

    assert result["overall"]["verdict"] == "UNVERIFIABLE"
    assert result["completion"]["verdict"] == "UNVERIFIABLE"
    assert "checker_missing" in result["completion"]["reasons"]


def test_synthetic_public_examples_cover_match_and_wrong_state():
    root = Path(__file__).resolve().parents[1] / "examples" / "evaluation" / "incident-sim"
    task = json.loads((root / "task.json").read_text(encoding="utf-8"))
    matching = json.loads((root / "matching-trace.json").read_text(encoding="utf-8"))
    wrong = json.loads((root / "wrong-state-trace.json").read_text(encoding="utf-8"))

    assert evaluate_incident_sim(task, matching)["overall"]["verdict"] == "MATCH"
    assert evaluate_incident_sim(task, wrong)["overall"]["verdict"] == "DRIFT"

from harness.evidence_json import canonical_sha256
from harness.incident_sim_input import IncidentSimValidationError
from harness.institutional_access import access_scope
from harness.incident_sim_eval import evaluate_incident_sim
import harness.incident_sim_packet as packet_mod
from harness.incident_sim_packet import build_process_audit_packet
import pytest


TASK = {
    "schema": "flywheel.incident-sim-task/v1",
    "task_id": "incident_sim_local_001",
    "task_version": "2026-09-13.1",
    "fixture_version": "fixture-2026-09-13.1",
    "spec_version": "incident-sim/v1",
    "scorer": {"id": "ordered-action-final-state", "version": "1"},
    "checker": {"id": "incident-sim-local-checker", "version": "1"},
    "roles": {"producer": "local-fixture", "checker": "flywheel"},
    "shared_dependencies": ["harness.incident_sim_eval", "harness.incident_sim_packet"],
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


def _keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from _keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _keys(child)


def test_packet_recomputes_evaluation_instead_of_sealing_forged_verdict():
    wrong = trace(final_state={"release": "SHIP", "status": "done"})
    forged = evaluate_incident_sim(TASK, trace())

    packet = build_process_audit_packet(TASK, wrong, supplied_evaluation=forged)

    assert packet["evaluation"]["overall"]["verdict"] == "DRIFT"
    assert packet["supplied_evaluation_check"]["verdict"] == "DRIFT"
    assert packet["receipts"]["work"]["seal"]["hex"]
    assert packet["receipt_verification"]["work"]["verdict"] == "MATCH"
    assert packet["receipt_verification"]["audit"]["verdict"] == "MATCH"
    assert any("EMET" in item for item in packet["integration_limits"])


def test_packet_carries_hashes_and_exact_source_pointers_with_values():
    good = trace()

    packet = build_process_audit_packet(TASK, good)

    assert packet["task_sha256"] == canonical_sha256(TASK)
    assert packet["trace_sha256"] == canonical_sha256(good)
    assert {
        "source": "task",
        "json_pointer": "/expected_final_state",
        "source_value": TASK["expected_final_state"],
    } in packet["source_values"]
    assert {
        "source": "trace",
        "json_pointer": "/final_state",
        "source_value": good["final_state"],
    } in packet["source_values"]
    assert {
        "source": "trace",
        "json_pointer": "/claimed_scores/0/value",
        "source_value": "PASS",
    } in packet["source_values"]


def test_packet_reuses_incident_case_proposal_and_receipt_layers():
    packet = build_process_audit_packet(TASK, trace())

    assert packet["incident"]["case"]["schema"] == "flywheel.incident-case/v1"
    assert packet["incident"]["proposal"]["schema"] == "flywheel.incident-proposed-graph/v1"
    assert len(packet["receipts"]["actions"]) == 3
    assert packet["receipt_verification"]["actions"]["verdict"] == "MATCH"
    assert packet["receipts"]["audit"]["prev_receipt_sha256"] == packet["receipts"]["work"]["seal"]["hex"]
    assert packet["receipt_verification"]["audit"]["audit_verdict"] == "PASS"
    assert packet["receipt_limitations"][0].startswith("Action receipts are reconstructed")


def test_missing_checker_evidence_cannot_become_a_passing_packet():
    missing = trace()
    missing.pop("checker")

    packet = build_process_audit_packet(TASK, missing)

    assert packet["evaluation"]["overall"]["verdict"] == "UNVERIFIABLE"
    assert packet["receipt_verification"]["audit"]["audit_verdict"] == "FAIL"
    assert "checker_missing" in packet["evaluation"]["completion"]["reasons"]
    assert "assessment independence" in " ".join(packet["independence"]["unknowns"])


def test_packet_rejects_oversize_trace_before_receipt_construction(monkeypatch):
    too_large = trace(observed_actions=[
        {"id": f"a{i}", "summary": "synthetic"} for i in range(300)
    ])

    def fail_if_called(**_kwargs):
        raise AssertionError("receipt construction should not run")

    monkeypatch.setattr(packet_mod, "build_receipt", fail_if_called)

    with pytest.raises(IncidentSimValidationError):
        build_process_audit_packet(TASK, too_large)


def test_packet_is_bounded_json_not_a_command_or_network_runner():
    packet = build_process_audit_packet(TASK, trace())

    assert packet["schema"] == "flywheel.incident-sim-process-audit/v1"
    assert packet["observation_scope"] == "fixture_expected_actions_only"
    assert "emet_receipt" not in packet
    banned = {"command", "network", "url", "raw_prompt", "api_payload"}
    assert not (set(_keys(packet)) & banned)



def _access_record(scope_doc):
    return {
        "schema": "flywheel.institutional-access/v1",
        "scope_sha256": scope_doc["scope_sha256"],
        "reviewer": {
            "role": "external_evaluator",
            "declared_conflicts": [],
            "relationship_to_producer": "unknown",
        },
        "events": [
            {
                "event_id": "task-grant",
                "sequence": 1,
                "evidence_ref": "task",
                "status": "granted",
                "stated_reason": "synthetic fixture declared access",
                "source_pointers": [{
                    "source_ref": "task",
                    "json_pointer": "/expected_final_state",
                    "source_value": TASK["expected_final_state"],
                }],
                "redactions": [],
            },
            {
                "event_id": "trace-grant",
                "sequence": 2,
                "evidence_ref": "trace",
                "status": "granted",
                "stated_reason": "synthetic fixture declared access",
                "source_pointers": [{
                    "source_ref": "trace",
                    "json_pointer": "/final_state",
                    "source_value": trace()["final_state"],
                }],
                "redactions": [],
            },
        ],
    }


def test_packet_default_has_no_institutional_access_assessment():
    packet = build_process_audit_packet(TASK, trace())

    assert "institutional_access" not in packet


def test_packet_can_include_synthetic_declared_access_component():
    good = trace()
    scope_doc = access_scope("incident-sim-synthetic", {"claim-final-state": ["task", "trace"]},
                             {"task": TASK, "trace": good})

    packet = build_process_audit_packet(
        TASK,
        good,
        institutional_access=_access_record(scope_doc),
        institutional_access_scope=scope_doc,
    )

    component = packet["institutional_access"]
    assert component["context"] == "synthetic_declared_access"
    assert component["assessment"]["coverage_assessment"] == "complete"
    assert "support" not in set(_keys(component))

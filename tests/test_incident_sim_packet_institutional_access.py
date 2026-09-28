
import json
from copy import deepcopy

from harness.evidence_json import canonical_sha256
from harness.institutional_access import access_scope
from harness.incident_sim_packet import build_process_audit_packet, verify_process_audit_packet
from tests.test_incident_sim_packet import TASK, trace, _access_record


def _json_roundtrip(value, *, sort_keys=False):
    return json.loads(json.dumps(value, sort_keys=sort_keys))


def _reverse_object_order(value):
    if isinstance(value, dict):
        return {key: _reverse_object_order(value[key]) for key in reversed(list(value))}
    if isinstance(value, list):
        return [_reverse_object_order(item) for item in value]
    return value


def test_packet_snapshots_task_trace_and_independence_against_later_mutation():
    task = deepcopy(TASK)
    good = trace()
    packet = build_process_audit_packet(task, good)
    before = canonical_sha256(packet)

    good["final_state"]["release"] = "SHIP"
    task["expected_final_state"]["release"] = "SHIP"
    task["roles"]["producer"] = "mutated"
    task["shared_dependencies"].append("mutated")

    assert canonical_sha256(packet) == before
    assert {"source": "trace", "json_pointer": "/final_state", "source_value": {"release": "HOLD", "status": "needs_review"}} in packet["source_values"]
    assert packet["independence"]["roles"] == {"producer": "local-fixture", "checker": "flywheel"}
    assert packet["independence"]["shared_dependencies"] == ["harness.incident_sim_eval", "harness.incident_sim_packet"]


def test_attached_institutional_component_mutation_fails_packet_verification():
    good = trace()
    scope_doc = access_scope("incident-sim-synthetic", {"claim-final-state": ["task", "trace"]},
                             {"task": TASK, "trace": good})
    packet = build_process_audit_packet(
        TASK,
        good,
        institutional_access=_access_record(scope_doc),
        institutional_access_scope=scope_doc,
    )

    assert verify_process_audit_packet(packet)["verdict"] == "MATCH"

    packet["institutional_access"]["assessment"]["coverage_assessment"] = "limited"

    result = verify_process_audit_packet(packet)
    assert result["verdict"] == "DRIFT"
    assert result["institutional_access_verdict"] == "DRIFT"


def test_packet_verifier_reports_absent_access_as_not_assessed_and_scope_explicit():
    result = verify_process_audit_packet(build_process_audit_packet(TASK, trace()))

    assert result["verdict"] == "MATCH"
    assert result["institutional_access_verdict"] == "NOT_ASSESSED"
    assert any(row["field"] == "/institutional_access" for row in result["unverified_fields"])
    assert any(row["field"] == "/evaluation" for row in result["verified_fields"])
    assert any("semantic correctness" in item for item in result["does_not_verify"])


def test_packet_verifier_rejects_visible_evaluation_mutation():
    packet = build_process_audit_packet(TASK, trace())
    packet["evaluation"]["overall"]["verdict"] = "FORGED"

    result = verify_process_audit_packet(packet)

    assert result["verdict"] == "DRIFT"
    assert result["evaluation_digest_verdict"] == "DRIFT"


def test_packet_verifier_rejects_source_values_mutation():
    packet = build_process_audit_packet(TASK, trace())
    packet["source_values"][0]["source_value"] = "FORGED"

    result = verify_process_audit_packet(packet)

    assert result["verdict"] == "DRIFT"
    assert result["source_values_digest_verdict"] == "DRIFT"


def test_packet_verifier_rejects_independence_mutation():
    packet = build_process_audit_packet(TASK, trace())
    packet["independence"]["roles"]["producer"] = "FORGED"

    result = verify_process_audit_packet(packet)

    assert result["verdict"] == "DRIFT"
    assert result["independence_digest_verdict"] == "DRIFT"


def test_packet_verifier_calls_lower_level_receipt_checks():
    packet = build_process_audit_packet(TASK, trace())
    packet["receipts"]["actions"][0]["tool"] = "FORGED"

    action_result = verify_process_audit_packet(packet)
    assert action_result["verdict"] == "DRIFT"
    assert action_result["action_chain_verdict"] == "TAMPERED"

    packet = build_process_audit_packet(TASK, trace())
    packet["receipts"]["work"]["tool"] = "FORGED"

    work_result = verify_process_audit_packet(packet)
    assert work_result["verdict"] == "DRIFT"
    assert work_result["work_receipt_verdict"] == "TAMPERED"

    packet = build_process_audit_packet(TASK, trace())
    packet["receipts"]["audit"]["verdict"] = "FAIL"

    audit_result = verify_process_audit_packet(packet)
    assert audit_result["verdict"] == "DRIFT"
    assert audit_result["audit_verdict"] == "TAMPERED"


def test_packet_verifier_rejects_other_visible_packet_value_mutation():
    packet = build_process_audit_packet(TASK, trace())
    packet["integration_limits"][0] = "FORGED"

    result = verify_process_audit_packet(packet)

    assert result["verdict"] == "DRIFT"
    assert result["packet_digest_verdict"] == "DRIFT"


def test_packet_verifier_accepts_sorted_and_reversed_receipt_key_order():
    packet = build_process_audit_packet(TASK, trace())

    sorted_packet = _json_roundtrip(packet, sort_keys=True)
    reversed_packet = _reverse_object_order(_json_roundtrip(packet))

    assert verify_process_audit_packet(sorted_packet)["verdict"] == "MATCH"
    assert verify_process_audit_packet(reversed_packet)["verdict"] == "MATCH"


def test_packet_verifier_does_not_mutate_order_adjusted_caller_packet():
    packet = _reverse_object_order(_json_roundtrip(build_process_audit_packet(TASK, trace())))
    before = json.dumps(packet, ensure_ascii=False)

    assert verify_process_audit_packet(packet)["verdict"] == "MATCH"

    assert json.dumps(packet, ensure_ascii=False) == before


def test_packet_verifier_sorted_order_still_rejects_tampered_values_and_missing_keys():
    packet = _json_roundtrip(build_process_audit_packet(TASK, trace()), sort_keys=True)
    packet["receipts"]["actions"][0]["tool"] = "FORGED"

    action_result = verify_process_audit_packet(packet)
    assert action_result["verdict"] == "DRIFT"
    assert action_result["action_chain_verdict"] == "TAMPERED"

    packet = _json_roundtrip(build_process_audit_packet(TASK, trace()), sort_keys=True)
    packet["receipts"].pop("work")
    before = json.dumps(packet, ensure_ascii=False)

    missing_result = verify_process_audit_packet(packet)
    assert missing_result["verdict"] == "DRIFT"
    assert missing_result["work_receipt_verdict"] == "DRIFT"
    assert "work" not in packet["receipts"]
    assert json.dumps(packet, ensure_ascii=False) == before

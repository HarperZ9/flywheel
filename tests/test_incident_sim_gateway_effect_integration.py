from __future__ import annotations

import json

from harness.gateway_agent_trace import AgentTrace, TraceLedger
from harness.gateway_effect_offline import build_gateway_effect_component
from harness.gateway_operation_process import WorkerOutcome
from harness.gateway_operation_recovery import LIFECYCLE
from harness.incident_sim_packet import build_process_audit_packet
from harness.incident_sim_packet_verify import verify_process_audit_packet
from tests.test_gateway_operation_recovery import OPERATION, _events, _queued, _started
from tests.test_gateway_operations import JOURNEY, OWNER, _service
from tests.test_incident_sim_packet import TASK, trace

PATH = "/api/incident-sim/process-audit/review"


def _write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _gateway_component(root):
    _started(root, _queued(root))
    agent_trace = AgentTrace(root, OWNER, JOURNEY, OPERATION)
    TraceLedger(agent_trace).append("tool_result", "private", {
        "tool": "write_file",
        "ok": True,
        "edited": {"incident.txt": "a" * 64},
    })
    service = _service(root)
    service._terminal(OWNER, OPERATION, WorkerOutcome(
        "completed", agent_trace.projection("completed")))
    lifecycle = [
        event for event in _events(root)
        if event["event_type"] in LIFECYCLE
        and event["payload"].get("operation_ref") == OPERATION
    ]
    return build_gateway_effect_component(
        terminal_result=service.result(OWNER, OPERATION),
        lifecycle_history=lifecycle,
        trace_records=agent_trace.read(),
    )


def _expected(component):
    hashes = component["packet_local_sha256"]
    return {"trace_records_sha256": hashes["trace_records"],
            "reference_provenance": "test controlled source"}


def test_packet_section_binds_gateway_effect_component(tmp_path):
    component = _gateway_component(tmp_path)

    packet = build_process_audit_packet(TASK, trace(), gateway_effect=component)
    verification = verify_process_audit_packet(packet)

    assert packet["gateway_effect"]["schema"] == "flywheel.gateway-effect-offline-component/v1"
    assert packet["section_sha256"]["/gateway_effect"]
    assert verification["gateway_effect_verification"]["internal_consistency"]["verdict"] == "MATCH"
    assert verification["gateway_effect_verdict"] == "MATCH"


def test_missing_gateway_effect_component_stays_unavailable_not_failure():
    packet = build_process_audit_packet(TASK, trace())

    verification = verify_process_audit_packet(packet)

    assert verification["verdict"] == "MATCH"
    assert verification["gateway_effect_verdict"] == "UNAVAILABLE"
    assert verification["gateway_effect_verification"]["effect_coverage"]["verdict"] == "UNAVAILABLE"


def test_review_api_accepts_expected_hashes_outside_packet(tmp_path):
    from harness.incident_sim_process_audit_route import process_audit_review_post

    component = _gateway_component(tmp_path)
    packet = build_process_audit_packet(TASK, trace(), gateway_effect=component)
    request = {
        "schema": "flywheel.incident-sim-process-audit-review-request/v1",
        "packet": packet,
        "expected_hashes": {
            "trace_records_sha256": "0" * 64,
            "reference_provenance": "wrong control",
        },
    }

    body, status = process_audit_review_post(
        PATH,
        json.dumps(request).encode("utf-8"),
        content_type="application/json",
    )

    assert status == 200
    assert body["assessment"] == "packet-local-match"
    assert body["gateway_effect_verification"]["expected_correspondence"]["verdict"] == "DRIFT"
    assert body["gateway_effect_verification"]["expected_correspondence"]["reference_provenance"] == "wrong control"


def test_review_api_derives_preview_without_echoing_forged_preview_metadata(tmp_path):
    from harness.incident_sim_process_audit_route import process_audit_review_post

    component = _gateway_component(tmp_path)
    component["trace_preview"] = {
        "record_count": 1,
        "record_kinds": {"secret-route-kind": 1},
        "sensitive_payload_categories": ["secret-route-category"],
    }
    packet = build_process_audit_packet(TASK, trace(), gateway_effect=component)

    body, status = process_audit_review_post(
        PATH,
        json.dumps(packet).encode("utf-8"),
        content_type="application/json",
    )

    encoded = json.dumps(body)
    assert status == 200
    assert "secret-route-kind" not in encoded
    assert "secret-route-category" not in encoded
    pointer = {
        row["json_pointer"]: row for row in body["source_pointers"]
    }["/gateway_effect/trace_preview"]
    assert pointer["source"] == "derived_from_submitted_trace_records"
    assert pointer["privacy"] == "content_free_preview"
    assert "private exact-review input" in " ".join(pointer["limits"])


def test_cli_verify_packet_uses_external_gateway_expected_hashes(tmp_path, capsys):
    from harness.incident_sim_cli import main

    component = _gateway_component(tmp_path / "state")
    packet = build_process_audit_packet(TASK, trace(), gateway_effect=component)
    packet_path = tmp_path / "packet.json"
    _write_json(packet_path, packet)

    assert main([
        "--verify-packet", str(packet_path),
        "--expected-gateway-trace-records-sha256", "0" * 64,
    ]) == 1
    drift = json.loads(capsys.readouterr().out)
    assert drift["verification"]["gateway_effect_verification"][
        "expected_correspondence"]["verdict"] == "DRIFT"

    assert main([
        "--verify-packet", str(packet_path),
        "--expected-gateway-trace-records-sha256",
        component["packet_local_sha256"]["trace_records"],
    ]) == 0
    matched = json.loads(capsys.readouterr().out)
    assert matched["verification"]["gateway_effect_verification"][
        "expected_correspondence"]["verdict"] == "MATCH"


def test_cli_can_build_packet_from_exact_gateway_source_files(tmp_path, capsys):
    from harness.incident_sim_cli import main

    component = _gateway_component(tmp_path / "state")
    task_path, trace_path = tmp_path / "task.json", tmp_path / "trace.json"
    terminal_path = tmp_path / "terminal.json"
    lifecycle_path = tmp_path / "lifecycle.json"
    records_path = tmp_path / "records.json"
    _write_json(task_path, TASK)
    _write_json(trace_path, trace())
    _write_json(terminal_path, component["terminal_result"])
    _write_json(lifecycle_path, component["lifecycle_history"])
    _write_json(records_path, component["trace_records"])

    assert main([
        "--task", str(task_path),
        "--trace", str(trace_path),
        "--gateway-terminal-result", str(terminal_path),
        "--gateway-lifecycle-history", str(lifecycle_path),
        "--gateway-trace-records", str(records_path),
    ]) == 0
    report = json.loads(capsys.readouterr().out)
    verification = verify_process_audit_packet(report["audit_packet"])

    assert verification["gateway_effect_verdict"] == "MATCH"


def test_review_api_rejects_oversized_gateway_effect_request_before_parse():
    from harness.incident_sim_process_audit_route import (
        MAX_PACKET_BYTES,
        process_audit_review_post,
    )

    body, status = process_audit_review_post(
        PATH,
        b'{"schema":"flywheel.incident-sim-process-audit-review-request/v1","pad":"'
        + b"x" * MAX_PACKET_BYTES + b'"}',
        content_type="application/json",
    )

    assert status == 413
    assert body["error"]["code"] == "PAYLOAD_TOO_LARGE"

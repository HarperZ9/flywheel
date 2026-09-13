import json

import pytest

from harness.evidence_json import canonical_sha256
from harness.gateway_agent_trace import AgentTrace, TraceLedger
from harness.gateway_agent_trace_route import read_trace
from harness.gateway_operations import cancel_operation, start_operation
from harness.gateway_operation_process import WorkerOutcome
from harness.gateway_operation_recovery import validate_operation_value
from harness.journey_store import JourneyStore, MutationCommand
from tests.test_gateway_operations import (
    Factory,
    Process,
    JOURNEY,
    NOW,
    OWNER,
    _authorized,
    _cancel_raw,
    _service,
)
from tests.test_gateway_operation_recovery import OPERATION, _queued, _started


def _append_terminal(root, head, event_type, payload):
    return JourneyStore(root).append(MutationCommand(
        OWNER, JOURNEY, head, "terminal", event_type,
        {"occurred_at": NOW, "payload": payload}))


def test_cancelled_terminal_projection_contains_retained_effect_evidence(tmp_path):
    process = Process()
    service = _service(tmp_path)
    queued = start_operation(
        authorized=_authorized(tmp_path), service=service,
        process_factory=Factory(process, tmp_path))
    assert process.resumed.wait(10), "worker never resumed"
    trace = AgentTrace(tmp_path, OWNER, JOURNEY, queued.operation_ref)
    TraceLedger(trace).append("tool_result", "private result", {
        "tool": "write_file", "ok": True,
        "edited": {"example.txt": "a" * 64},
    })

    terminal = cancel_operation(
        action="operation.cancel",
        raw=(raw := _cancel_raw(service.snapshot(OWNER, queued.operation_ref),
                                queued.operation_ref)),
        owner_ref=OWNER,
        service=service,
    )
    replay = cancel_operation(
        action="operation.cancel", raw=raw, owner_ref=OWNER, service=service)
    result = service.result(OWNER, queued.operation_ref)["result"]

    assert terminal.state == result["state"] == "cancelled"
    assert replay.result_sha256 == terminal.result_sha256
    evidence = result["effect_evidence"]
    assert evidence["known_observation_count"] == 1
    assert evidence["known_observations"][0]["record_sha256"] == trace.head
    assert "NOT_ROLLBACK" in evidence["unknown_effect_scope"]
    assert "example.txt" not in json.dumps(result)
    assert "private result" not in json.dumps(result)


def test_rehashed_fabricated_effect_evidence_is_rejected_on_result_read(tmp_path):
    queued = _queued(tmp_path)
    started = _started(tmp_path, queued)
    trace = AgentTrace(tmp_path, OWNER, JOURNEY, OPERATION)
    trace.append("progress", {"status": "running"})
    projection = trace.projection("completed")
    projection.pop("projection_sha256")
    projection["effect_evidence"] = {
        "schema": "flywheel.gateway-effect-evidence/v1",
        "scope": "owner_private_trace_prefix",
        "basis": {
            "trace_ref": trace.ref,
            "record_count": 1,
            "trace_head_sha256": trace.head,
            "terminal_state": "completed",
            "terminal_basis_event_type": "operation_started",
            "terminal_basis_event_sha256": started.event_sha256,
        },
        "known_observation_count": 1,
        "known_observations_omitted": 0,
        "known_observations_digest": canonical_sha256([{
            "kind": "tool_result_edit_fingerprint",
            "trace_sequence": 0,
            "record_sha256": trace.head,
            "record_kind": "ledger",
            "payload_kind": "tool_result",
            "json_pointer": "/payload/meta/edited",
            "value_sha256": "e" * 64,
        }]),
        "known_observations": [{
            "kind": "tool_result_edit_fingerprint",
            "trace_sequence": 0,
            "record_sha256": trace.head,
            "record_kind": "ledger",
            "payload_kind": "tool_result",
            "json_pointer": "/payload/meta/edited",
            "value_sha256": "e" * 64,
        }],
        "action_witness": {"status": "absent"},
        "tool_call_receipts": {"status": "absent"},
        "unknown_effect_scope": [
            "NOT_ROLLBACK",
            "NOT_EFFECT_ABSENCE",
            "NOT_CURRENT_FILESYSTEM_STATE",
            "UNRECORDED_ACTIONS_NOT_EXCLUDED",
            "TOOLS_WITHOUT_POST_EFFECT_FINGERPRINTS_REMAIN_UNKNOWN",
            "EFFECTS_AFTER_TRACE_HEAD_REMAIN_UNKNOWN",
        ],
        "does_not_prove": [
            "semantic correctness",
            "complete workstation observation",
            "current filesystem state",
            "absence of effects outside the accepted trace prefix",
            "rollback or remote cancellation",
        ],
    }
    projection["projection_sha256"] = canonical_sha256(projection)
    service = _service(tmp_path)
    digest = service._seal(OWNER, OPERATION, "agent.run", "completed",
                           projection)
    _append_terminal(tmp_path, started.event_head_sha256,
                     "operation_completed", {
        "operation_ref": OPERATION,
        "basis_event_sha256": started.event_sha256,
        "result_sha256": digest,
    })

    with pytest.raises(Exception) as failure:
        service.result(OWNER, OPERATION)
    assert getattr(failure.value, "code", None) == "STORE_COMMIT_FAILED"


def test_worker_supplied_effect_summary_is_replaced_before_sealing(tmp_path):
    queued = _queued(tmp_path)
    _started(tmp_path, queued)
    trace = AgentTrace(tmp_path, OWNER, JOURNEY, OPERATION)
    TraceLedger(trace).append("tool_result", "private result", {
        "tool": "write_file", "ok": True,
        "edited": {"kept-private.txt": "b" * 64},
    })
    projection = trace.projection("completed")
    projection["effect_evidence"] = {"schema": "fake"}
    validate_operation_value(projection)
    service = _service(tmp_path)

    terminal = service._terminal(
        OWNER, OPERATION, WorkerOutcome("completed", projection))
    result = service.result(OWNER, OPERATION)["result"]

    assert terminal.state == "completed"
    assert result["effect_evidence"]["known_observation_count"] == 1
    assert result["effect_evidence"]["schema"] != "fake"
    assert "kept-private.txt" not in json.dumps(result)


def test_completed_after_cancel_keeps_completed_state_and_cancel_basis(tmp_path):
    class CompletionWins(Process):
        def signal_tree(self):
            self.signal_calls += 1
            self.outcome = WorkerOutcome("completed", trace.projection("completed"))
            self.ready.set()
            return True

    process = CompletionWins()
    service = _service(tmp_path)
    queued = start_operation(
        authorized=_authorized(tmp_path), service=service,
        process_factory=Factory(process, tmp_path))
    assert process.resumed.wait(10), "worker never resumed"
    trace = AgentTrace(tmp_path, OWNER, JOURNEY, queued.operation_ref)
    TraceLedger(trace).append("tool_result", "private result", {
        "tool": "write_file", "ok": True,
        "edited": {"race.txt": "c" * 64},
    })

    terminal = cancel_operation(
        action="operation.cancel",
        raw=_cancel_raw(service.snapshot(OWNER, queued.operation_ref),
                        queued.operation_ref),
        owner_ref=OWNER,
        service=service,
    )
    result = service.result(OWNER, queued.operation_ref)["result"]

    assert terminal.state == result["state"] == "completed"
    assert result["effect_evidence"]["basis"]["terminal_state"] == "completed"
    assert result["effect_evidence"]["basis"][
        "terminal_basis_event_type"] == "cancel_requested"
    assert "NOT_EFFECT_ABSENCE" in result["effect_evidence"]["unknown_effect_scope"]


def test_failed_terminal_projection_retains_prior_effect_observation(tmp_path):
    _started(tmp_path, _queued(tmp_path))
    trace = AgentTrace(tmp_path, OWNER, JOURNEY, OPERATION)
    TraceLedger(trace).append("tool_result", "private result", {
        "tool": "apply_patch", "ok": True,
        "edited": {"patched.txt": "4" * 64},
    })
    service = _service(tmp_path)

    terminal = service._terminal(
        OWNER, OPERATION,
        WorkerOutcome("failed", {"reason": "EXTERNAL_ACTION_FAILED"}))
    result = service.result(OWNER, OPERATION)["result"]

    assert terminal.state == result["state"] == "failed"
    assert result["reason"] == "EXTERNAL_ACTION_FAILED"
    assert result["effect_evidence"]["known_observation_count"] == 1


def test_cancelled_terminal_with_unsupported_metadata_preserves_unknown_scope(tmp_path):
    process = Process()
    service = _service(tmp_path)
    queued = start_operation(
        authorized=_authorized(tmp_path), service=service,
        process_factory=Factory(process, tmp_path))
    assert process.resumed.wait(10), "worker never resumed"
    trace = AgentTrace(tmp_path, OWNER, JOURNEY, queued.operation_ref)
    TraceLedger(trace).append("tool_result", "private result", {
        "tool": [], "ok": True,
        "edited": {"unsupported.txt": "7" * 64},
    })

    terminal = cancel_operation(
        action="operation.cancel",
        raw=_cancel_raw(service.snapshot(OWNER, queued.operation_ref),
                        queued.operation_ref),
        owner_ref=OWNER,
        service=service,
    )
    result = service.result(OWNER, queued.operation_ref)["result"]

    assert terminal.state == result["state"] == "cancelled"
    assert result["effect_evidence"]["known_observation_count"] == 0
    assert "NOT_EFFECT_ABSENCE" in result["effect_evidence"]["unknown_effect_scope"]
    assert "unsupported.txt" not in json.dumps(result)


def test_legacy_projection_without_effect_evidence_still_reads(tmp_path):
    queued = _queued(tmp_path)
    started = _started(tmp_path, queued)
    trace = AgentTrace(tmp_path, OWNER, JOURNEY, OPERATION)
    TraceLedger(trace).append("tool_result", "private result", {
        "tool": "write_file", "ok": True,
        "edited": {"legacy.txt": "5" * 64},
    })
    service = _service(tmp_path)
    digest = service._seal(
        OWNER, OPERATION, "agent.run", "completed",
        trace.projection("completed"))
    _append_terminal(tmp_path, started.event_head_sha256,
                     "operation_completed", {
        "operation_ref": OPERATION,
        "basis_event_sha256": started.event_sha256,
        "result_sha256": digest,
    })

    result = service.result(OWNER, OPERATION)["result"]

    assert result["state"] == "completed"
    assert "effect_evidence" not in result


def test_trace_tamper_after_terminal_fails_effect_validation(tmp_path):
    _started(tmp_path, _queued(tmp_path))
    trace = AgentTrace(tmp_path, OWNER, JOURNEY, OPERATION)
    TraceLedger(trace).append("tool_result", "private result", {
        "tool": "write_file", "ok": True,
        "edited": {"tamper.txt": "6" * 64},
    })
    service = _service(tmp_path)
    service._terminal(OWNER, OPERATION,
                      WorkerOutcome("completed", trace.projection("completed")))
    detail = read_trace(service, OWNER, OPERATION,
                        f"ref={trace.ref}&sequence=0")
    assert detail["record"]["record_sha256"] == trace.head
    path = trace.root / trace.base / "00000000.json"
    path.write_text(path.read_text().replace("private result", "tampered"))

    with pytest.raises(Exception) as failure:
        service.result(OWNER, OPERATION)
    assert getattr(failure.value, "code", None) == "STORE_COMMIT_FAILED"
    with pytest.raises(Exception) as trace_failure:
        read_trace(service, OWNER, OPERATION, f"ref={trace.ref}&sequence=0")
    assert getattr(trace_failure.value, "code", None) == "STORE_COMMIT_FAILED"

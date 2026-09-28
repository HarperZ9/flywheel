from harness.gateway_agent_projection import validate_projection
from harness.gateway_agent_trace import AgentTrace, TraceLedger
from harness.gateway_effect_binding import attach_terminal_effect_evidence
from harness.gateway_operation_process import WorkerOutcome
from tests.test_gateway_operations import JOURNEY, OWNER, _service
from tests.test_gateway_operation_recovery import OPERATION, _queued, _started


def _break_derivation(monkeypatch):
    monkeypatch.setattr(
        "harness.gateway_effect_binding.derive_effect_evidence",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("boom")))


def _trace_with_effect(root):
    trace = AgentTrace(root, OWNER, JOURNEY, OPERATION)
    TraceLedger(trace).append("tool_result", "private result", {
        "tool": "write_file", "ok": True,
        "edited": {"fallback.txt": "8" * 64},
    })
    return trace


def test_attach_derivation_failure_preserves_valid_legacy_projection(
        tmp_path, monkeypatch):
    started = _started(tmp_path, _queued(tmp_path))
    trace = _trace_with_effect(tmp_path)
    projection = trace.projection("completed")
    _break_derivation(monkeypatch)
    basis = {"event_type": "operation_started",
             "event_sha256": started.event_sha256}

    result = attach_terminal_effect_evidence(
        tmp_path, OWNER, JOURNEY, OPERATION, projection, "completed", basis)

    assert result == projection
    validate_projection(result, trace.binding)


def test_terminal_derivation_failure_keeps_state_and_legacy_projection(
        tmp_path, monkeypatch):
    _started(tmp_path, _queued(tmp_path))
    trace = _trace_with_effect(tmp_path)
    _break_derivation(monkeypatch)
    service = _service(tmp_path)

    terminal = service._terminal(
        OWNER, OPERATION, WorkerOutcome("completed", trace.projection("completed")))
    result = service.result(OWNER, OPERATION)["result"]

    assert terminal.state == result["state"] == "completed"
    assert "effect_evidence" not in result
    validate_projection(result, trace.binding)

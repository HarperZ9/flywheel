import pytest

from harness.evidence_json import canonical_sha256
from harness.gateway_agent_trace import AgentTrace, TraceLedger
from harness.gateway_effect_binding import (
    attach_terminal_effect_evidence,
    validate_terminal_effect_evidence,
)
from harness.gateway_effect_evidence import derive_effect_evidence
from harness.gateway_operation_process import WorkerOutcome
from tests.test_gateway_operations import JOURNEY, OWNER, _service
from tests.test_gateway_operation_recovery import OPERATION, _queued, _started


MUTATIONS = (
    ("state", "cancelled"),
    ("operation_ref", "op_" + "b" * 32),
    ("journey_ref", "jrn_" + "b" * 32),
)


def _records_and_projection(root, state="completed"):
    trace = AgentTrace(root, OWNER, JOURNEY, OPERATION)
    TraceLedger(trace).append("tool_result", "private result", {
        "tool": "write_file", "ok": True,
        "edited": {"binding.txt": "9" * 64},
    })
    return trace, trace.projection(state)


def _mutate_projection(projection, field, value):
    mutated = dict(projection)
    mutated[field] = value
    mutated.pop("projection_sha256", None)
    mutated["projection_sha256"] = canonical_sha256(mutated)
    return mutated


def _with_effect(projection, trace, records, started, field, value):
    projected = dict(projection)
    projected.pop("projection_sha256")
    projected["effect_evidence"] = derive_effect_evidence(
        records,
        trace_ref=trace.ref,
        terminal_state="completed",
        terminal_basis_event_type="operation_started",
        terminal_basis_event_sha256=started.event_sha256,
    )
    return _mutate_projection(projected, field, value)


@pytest.mark.parametrize("field,value", MUTATIONS)
def test_attach_rejects_malformed_nested_projection_binding(
        tmp_path, field, value):
    started = _started(tmp_path, _queued(tmp_path))
    trace, projection = _records_and_projection(tmp_path)
    mutated = _mutate_projection(projection, field, value)
    basis = {"event_type": "operation_started",
             "event_sha256": started.event_sha256}

    with pytest.raises(ValueError):
        attach_terminal_effect_evidence(
            tmp_path, OWNER, JOURNEY, OPERATION, mutated, "completed", basis)


@pytest.mark.parametrize("field,value", MUTATIONS)
def test_terminal_malformed_nested_projection_seals_typed_failure(
        tmp_path, field, value):
    _started(tmp_path, _queued(tmp_path))
    trace, projection = _records_and_projection(tmp_path)
    mutated = _mutate_projection(projection, field, value)
    service = _service(tmp_path)

    terminal = service._terminal(
        OWNER, OPERATION, WorkerOutcome("completed", mutated))
    result = service.result(OWNER, OPERATION)["result"]

    assert terminal.state == "failed"
    assert result == {"reason": "EXTERNAL_ACTION_FAILED"}


@pytest.mark.parametrize("field,value", MUTATIONS)
def test_read_rejects_rehashed_malformed_nested_projection_binding(
        tmp_path, field, value):
    queued = _queued(tmp_path)
    started = _started(tmp_path, queued)
    trace, projection = _records_and_projection(tmp_path)
    records = trace.read()
    mutated = _with_effect(projection, trace, records, started, field, value)
    service = _service(tmp_path)
    digest = service._seal(OWNER, OPERATION, "agent.run", "completed", mutated)
    from tests.test_gateway_effect_terminal import _append_terminal
    _append_terminal(tmp_path, started.event_head_sha256,
                     "operation_completed", {
        "operation_ref": OPERATION,
        "basis_event_sha256": started.event_sha256,
        "result_sha256": digest,
    })
    history = service._history(service._journey(OWNER), OPERATION)

    with pytest.raises(ValueError):
        validate_terminal_effect_evidence(
            tmp_path, OWNER, JOURNEY, OPERATION, mutated, history)
    with pytest.raises(Exception) as failure:
        service.result(OWNER, OPERATION)
    assert getattr(failure.value, "code", None) == "STORE_COMMIT_FAILED"

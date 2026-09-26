"""N-12, EN-C3, I3: a refused record ends the private trace with one
fixed-schema failure record in a reserved slot, and the refused value's bytes
reach no trace file. The public code stays PRIVATE_TRACE_UNAVAILABLE."""
import pytest

from harness import gateway_agent_trace as trace_module
from harness.gateway_agent_trace import AgentTrace, TraceError
from trace_redact_fakes import credential_fakes

OWNER = "owner_" + "a" * 32
JOURNEY = "jrn_" + "b" * 32
OPERATION = "op_" + "c" * 32


def _trace(state):
    state.mkdir(parents=True, exist_ok=True)
    return AgentTrace(state, OWNER, JOURNEY, OPERATION)


def _bytes(state) -> bytes:
    return b"".join(p.read_bytes() for p in state.rglob("*") if p.is_file())


def test_a_credential_refusal_leaves_class_rule_and_sequence_and_no_value(tmp_path):
    state = tmp_path / "state"
    trace = _trace(state)
    trace.append("request", {"goal": "list files"})
    fake = credential_fakes()["github_token"]
    with pytest.raises(TraceError) as refused:
        trace.append("ledger", {"kind": "tool", "content": f"cat .env printed {fake}"})
    assert str(refused.value) == "PRIVATE_TRACE_UNAVAILABLE"
    assert refused.value.failure_class == "credential_refused"
    with pytest.raises(TraceError):
        trace.append("ledger", {"kind": "tool", "content": "a later step"})
    trace_module.record_failure(trace, refused.value)
    records = _trace(state).read()
    assert [r["kind"] for r in records] == ["request", "failure"]
    assert records[-1]["payload"] == {
        "schema": "flywheel.gateway-agent-failure/v1", "class": "credential_refused",
        "rule": "github_token", "sequence": 1}
    assert fake.encode() not in _bytes(state)


def test_a_value_no_catalog_rule_names_is_unclassified(tmp_path):
    state = tmp_path / "state"
    trace = _trace(state)
    with pytest.raises(TraceError) as refused:
        trace.append("ledger", {"argv": ["curl", "-H", "x"]})
    trace_module.record_failure(trace, refused.value)
    payload = _trace(state).read()[-1]["payload"]
    assert payload["class"] == "credential_refused" and payload["rule"] == "unclassified"


def test_an_ordinary_failure_keeps_its_diagnostic_record(tmp_path):
    state = tmp_path / "state"
    trace = _trace(state)
    trace_module.record_failure(trace, RuntimeError("OPERATION_DEADLINE_EXCEEDED"))
    record = _trace(state).read()[-1]
    assert record["kind"] == "failure"
    assert record["payload"] == {"error_type": "RuntimeError",
                                 "message": "OPERATION_DEADLINE_EXCEEDED"}


def test_the_regular_bound_leaves_one_slot_for_the_failure_record(tmp_path, monkeypatch):
    assert trace_module.REGULAR_RECORDS == trace_module.MAX_RECORDS - 1 == 2047
    assert trace_module.REGULAR_BYTES == trace_module.MAX_TRACE_BYTES - 64 * 1024
    monkeypatch.setattr(trace_module, "MAX_RECORDS", 5)
    monkeypatch.setattr(trace_module, "REGULAR_RECORDS", 4)
    state = tmp_path / "state"
    trace = _trace(state)
    for index in range(4):
        trace.append("progress", {"step": index})
    with pytest.raises(TraceError) as bound:
        trace.append("progress", {"step": 4})
    assert bound.value.failure_class == "size_bound"
    trace_module.record_failure(trace, bound.value)
    with pytest.raises(TraceError):
        trace.append_failure("size_bound")
    with pytest.raises(TraceError):
        trace.append("progress", {"step": 5})
    records = _trace(state).read()
    assert len(records) == 5
    assert records[-1]["payload"]["class"] == "size_bound"
    assert records[-1]["payload"]["rule"] is None
    assert records[-1]["payload"]["sequence"] == 4


def test_a_failure_record_is_validated_by_its_own_narrow_check(tmp_path):
    trace = _trace(tmp_path / "state")
    with pytest.raises(TraceError):
        trace.append_failure("not_a_class")
    with pytest.raises(TraceError):
        trace.append_failure("credential_refused", rule="has spaces and text")

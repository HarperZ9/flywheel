import hashlib
import json

from harness.evidence_json import canonical_sha256

from test_claude_provider_session_support import (
    Events,
    FakeClient,
    OPREF,
    adapter_for,
    operation,
    request,
)


HISTORY = [
    {"type": "user", "uuid": "u1"},
    {"type": "assistant", "uuid": "a1"},
]


SOURCE = {
    "provider": "claude",
    "native_session_id": "session-a",
    "native_thread_id": "",
    "native_turn_id": "",
    "last_provider_event_id": "event-9",
    "config_digest": "cfg-a",
    "capability_digest": "cap-a",
}


TERMINAL = {
    "provider": "claude",
    "native_session_id": "session-a",
    "source_operation_ref": OPREF,
    "last_provider_event_id": "event-9",
    "input_sha256": "input-hash",
    "terminal_result_sha256": "terminal-hash",
    "source_input_receipt_sha256": "source-input-receipt-hash",
    "source_result_sha256": "source-result-hash",
    "source_terminal_event_sha256": "source-terminal-event-hash",
    "source_trace_head_sha256": "source-trace-head-hash",
    "history_store_head_sha256": canonical_sha256(HISTORY),
}


SOURCE_CONTEXT = {
    "operation_ref": OPREF,
    "input_sha256": "input-hash",
    "input_receipt_sha256": "source-input-receipt-hash",
    "result_sha256": "source-result-hash",
    "terminal_event_sha256": "source-terminal-event-hash",
    "trace_head_sha256": "source-trace-head-hash",
    "history_status": "missing_native_history",
    "side_effect_status": "input_sent",
    "provider_session": SOURCE,
}


def reconcile_operation(**changes):
    value = operation(
        target_operation_ref=OPREF,
    )
    value.update(changes)
    return value


def request_with_runtime_evidence(tmp_path, op=None, terminal=TERMINAL,
                                  history=HISTORY, source_context=SOURCE_CONTEXT,
                                  omit_history_sha=False,
                                  omit_terminal_sha=False):
    evidence = {}
    if history is not None:
        raw = "\n".join(json.dumps(record) for record in history).encode()
        path = tmp_path / "owned" / "session.jsonl"
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(raw)
        evidence["owned_history"] = {
            "type": "jsonl", "path": "owned/session.jsonl",
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
        if omit_history_sha:
            del evidence["owned_history"]["sha256"]
    if terminal is not None:
        raw = json.dumps(terminal, separators=(",", ":")).encode()
        path = tmp_path / "owned" / "terminal.json"
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(raw)
        evidence["terminal_observation"] = {
            "type": "json", "path": "owned/terminal.json",
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
        if omit_terminal_sha:
            del evidence["terminal_observation"]["sha256"]
    req = request(
        op or reconcile_operation(), source=SOURCE,
        action="provider.session.reconcile")
    object.__setattr__(req, "runtime_evidence", evidence)
    object.__setattr__(req, "source_context", source_context)
    object.__setattr__(req, "state_root", tmp_path)
    return req


def test_claude_reconcile_ignores_operation_authored_history_and_terminal():
    forged = reconcile_operation(
        owned_history=HISTORY, terminal_observation=TERMINAL,
        input_sha256="input-hash")

    outcome = adapter_for(FakeClient()).reconcile(
        request(forged, source=SOURCE, action="provider.session.reconcile"),
        emit=Events(),
    )

    assert outcome.state == "failed"
    assert outcome.result["reason"] == "AGENT_NATIVE_INCOMPLETE"
    assert outcome.result["detail_code"] == "missing_runtime_evidence"


def test_claude_reconcile_returns_native_terminal_observation_for_runtime_evidence(tmp_path):
    outcome = adapter_for(FakeClient()).reconcile(
        request_with_runtime_evidence(tmp_path),
        emit=Events(),
    )

    assert outcome.state == "completed"
    result = outcome.result
    assert result["history_status"] == "complete"
    assert result["side_effect_status"] == "native_terminal_observed"
    assert result["provider_session"] == SOURCE
    assert result["target_operation_ref"] == OPREF
    assert "native_history" not in result
    assert result["provider_observation"] == {
        "provider": "claude",
        "native_session_id": "session-a",
        "native_thread_id": "",
        "native_turn_id": "",
        "last_provider_event_id": "event-9",
        "config_digest": "cfg-a",
        "capability_digest": "cap-a",
        "target_operation_ref": OPREF,
        "observed_status": "native_terminal_observed",
    }
    assert result["positive_observation_ref"] == {
        "kind": "claude_owned_terminal_observation",
        "last_provider_event_id": "event-9",
        "terminal_result_sha256": "terminal-hash",
        "history_store_head_sha256": canonical_sha256(HISTORY),
    }


def test_claude_reconcile_missing_history_stays_incomplete(tmp_path):
    outcome = adapter_for(FakeClient()).reconcile(
        request_with_runtime_evidence(tmp_path, history=[]),
        emit=Events(),
    )

    assert outcome.state == "failed"
    assert outcome.result["reason"] == "AGENT_NATIVE_INCOMPLETE"
    assert outcome.result["history_status"] == "missing"
    assert outcome.result["side_effect_status"] == "indeterminate"


def test_claude_reconcile_rejects_mismatched_terminal_session(tmp_path):
    terminal = {**TERMINAL, "native_session_id": "other-session"}

    outcome = adapter_for(FakeClient()).reconcile(
        request_with_runtime_evidence(tmp_path, terminal=terminal),
        emit=Events(),
    )

    assert outcome.state == "failed"
    assert outcome.result["reason"] == "AGENT_BINDING_DRIFT"
    assert outcome.result["detail_code"] == "native_session_mismatch"


def test_claude_reconcile_requires_terminal_observation_not_history_only(tmp_path):
    outcome = adapter_for(FakeClient()).reconcile(
        request_with_runtime_evidence(tmp_path, terminal=None),
        emit=Events(),
    )

    assert outcome.state == "failed"
    assert outcome.result["reason"] == "AGENT_NATIVE_INCOMPLETE"
    assert outcome.result["history_status"] == "indeterminate"
    assert outcome.result["detail_code"] == "missing_terminal_observation"


def test_claude_reconcile_rejects_unpinned_history_pointer(tmp_path):
    outcome = adapter_for(FakeClient()).reconcile(
        request_with_runtime_evidence(tmp_path, omit_history_sha=True),
        emit=Events(),
    )

    assert outcome.state == "failed"
    assert outcome.result["reason"] == "AGENT_BINDING_DRIFT"
    assert outcome.result["detail_code"] == "missing_owned_pointer_sha256"


def test_claude_reconcile_rejects_unpinned_terminal_pointer(tmp_path):
    outcome = adapter_for(FakeClient()).reconcile(
        request_with_runtime_evidence(tmp_path, omit_terminal_sha=True),
        emit=Events(),
    )

    assert outcome.state == "failed"
    assert outcome.result["reason"] == "AGENT_BINDING_DRIFT"
    assert outcome.result["detail_code"] == "missing_owned_pointer_sha256"

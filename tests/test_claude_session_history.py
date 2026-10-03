import json
import hashlib

import pytest

from harness.evidence_json import canonical_sha256
from harness.provider_session_contract import ProviderSessionError

from harness.claude_session_history import (
    load_owned_history,
    load_owned_terminal_observation,
    observe_source_history,
)


SOURCE = {
    "operation_ref": "op_11111111111111111111111111111111",
    "side_effect_status": "input_sent",
    "input_sha256": "input-hash",
    "input_receipt_sha256": "source-input-receipt-hash",
    "result_sha256": "source-result-hash",
    "terminal_event_sha256": "source-terminal-event-hash",
    "trace_head_sha256": "source-trace-head-hash",
    "provider_session": {
        "provider": "claude",
        "native_session_id": "session-a",
        "native_thread_id": "",
        "native_turn_id": "",
        "last_provider_event_id": "event-9",
        "config_digest": "cfg-a",
        "capability_digest": "cap-a",
    },
}


OPAQUE_RECORDS = [
    {"type": "user", "uuid": "u1", "timestamp": "1970-01-01T00:00:00Z"},
    {"type": "assistant", "uuid": "a1", "timestamp": "1970-01-01T00:00:01Z"},
]


TERMINAL = {
    "provider": "claude",
    "native_session_id": "session-a",
    "source_operation_ref": "op_11111111111111111111111111111111",
    "last_provider_event_id": "event-9",
    "input_sha256": "input-hash",
    "terminal_result_sha256": "terminal-hash",
    "source_input_receipt_sha256": "source-input-receipt-hash",
    "source_result_sha256": "source-result-hash",
    "source_terminal_event_sha256": "source-terminal-event-hash",
    "source_trace_head_sha256": "source-trace-head-hash",
    "history_store_head_sha256": canonical_sha256(OPAQUE_RECORDS),
}


def test_observe_source_history_binds_terminal_observation_to_opaque_records():
    observed = observe_source_history(OPAQUE_RECORDS, SOURCE, TERMINAL)

    assert observed.status == "native_terminal_observed"
    assert observed.provider_session == SOURCE["provider_session"]
    assert observed.last_provider_event_id == "event-9"
    assert observed.input_sha256 == "input-hash"
    assert observed.terminal_result_sha256 == "terminal-hash"
    assert observed.history_store_head_sha256 == canonical_sha256(OPAQUE_RECORDS)
    assert observed.detail_code == "terminal_observation_bound"


def test_missing_terminal_observation_is_indeterminate_not_transcript_success():
    observed = observe_source_history(OPAQUE_RECORDS, SOURCE, None)

    assert observed.status == "indeterminate"
    assert observed.detail_code == "missing_terminal_observation"


def test_session_mismatch_is_indeterminate_for_caller_binding_drift():
    terminal = {**TERMINAL, "native_session_id": "other-session"}

    observed = observe_source_history(OPAQUE_RECORDS, SOURCE, terminal)

    assert observed.status == "indeterminate"
    assert observed.detail_code == "native_session_mismatch"


def test_mirror_error_keeps_history_indeterminate():
    records = [*OPAQUE_RECORDS, {"type": "system", "subtype": "mirror_error"}]

    observed = observe_source_history(records, SOURCE, TERMINAL)

    assert observed.status == "indeterminate"
    assert observed.detail_code == "mirror_error"


def test_missing_history_after_attempted_input_is_not_confirmed_not_applied():
    observed = observe_source_history([], SOURCE, TERMINAL)

    assert observed.status == "missing"
    assert observed.detail_code == "missing_history"


def test_load_owned_history_reads_only_relative_jsonl_under_state_root(tmp_path):
    history = tmp_path / "owned" / "session.jsonl"
    history.parent.mkdir()
    raw = "\n".join(json.dumps(record) for record in OPAQUE_RECORDS).encode()
    history.write_bytes(raw)

    assert load_owned_history({
        "type": "jsonl", "path": "owned/session.jsonl",
        "sha256": hashlib.sha256(raw).hexdigest(),
    }, state_root=tmp_path) == OPAQUE_RECORDS
    with pytest.raises(ProviderSessionError) as absolute:
        load_owned_history({"type": "jsonl", "path": str(history)}, state_root=tmp_path)
    assert absolute.value.code == "AGENT_BINDING_DRIFT"
    with pytest.raises(ProviderSessionError) as traversal:
        load_owned_history({"type": "jsonl", "path": "../session.jsonl"}, state_root=tmp_path)
    assert traversal.value.code == "AGENT_BINDING_DRIFT"
    with pytest.raises(ProviderSessionError) as unpinned:
        load_owned_history({"type": "jsonl", "path": "owned/session.jsonl"},
                           state_root=tmp_path)
    assert unpinned.value.code == "AGENT_BINDING_DRIFT"
    assert unpinned.value.detail["detail_code"] == "missing_owned_pointer_sha256"
    with pytest.raises(ProviderSessionError) as malformed:
        load_owned_history({
            "type": "jsonl", "path": "owned/session.jsonl",
            "sha256": hashlib.sha256(raw).hexdigest().upper(),
        }, state_root=tmp_path)
    assert malformed.value.code == "AGENT_BINDING_DRIFT"
    assert malformed.value.detail["detail_code"] == "invalid_owned_pointer_sha256"


def test_load_owned_terminal_observation_requires_pinned_owned_json(tmp_path):
    terminal = tmp_path / "owned" / "terminal.json"
    terminal.parent.mkdir()
    raw = json.dumps(TERMINAL, separators=(",", ":")).encode()
    terminal.write_bytes(raw)

    assert load_owned_terminal_observation({
        "type": "json", "path": "owned/terminal.json",
        "sha256": hashlib.sha256(raw).hexdigest(),
    }, state_root=tmp_path) == TERMINAL
    with pytest.raises(ProviderSessionError) as drift:
        load_owned_terminal_observation({
            "type": "json", "path": "owned/terminal.json",
            "sha256": "0" * 64,
        }, state_root=tmp_path)
    assert drift.value.code == "AGENT_BINDING_DRIFT"
    with pytest.raises(ProviderSessionError) as unpinned:
        load_owned_terminal_observation({
            "type": "json", "path": "owned/terminal.json",
        }, state_root=tmp_path)
    assert unpinned.value.code == "AGENT_BINDING_DRIFT"
    assert unpinned.value.detail["detail_code"] == "missing_owned_pointer_sha256"


def test_terminal_observation_must_bind_source_trace_and_store_head():
    terminal = {**TERMINAL, "history_store_head_sha256": "other-store"}

    observed = observe_source_history(OPAQUE_RECORDS, SOURCE, terminal)

    assert observed.status == "indeterminate"
    assert observed.detail_code == "history_store_head_mismatch"

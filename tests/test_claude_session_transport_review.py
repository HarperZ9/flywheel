import json
import math
import queue
import threading

import pytest

from harness.claude_session_contract import (
    ClaudeControlRequest,
    ClaudePermissionDecision,
)
from harness.claude_session_transport import (
    ClaudeSessionTransport,
    ClaudeSessionTransportError,
)
from harness.claude_session_wire import validate_result_frame


class Inbound:
    def __init__(self):
        self._lines = queue.Queue()

    def push(self, message):
        raw = json.dumps(message, separators=(",", ":")).encode("utf-8")
        self._lines.put(raw + b"\n")

    def push_raw(self, raw):
        self._lines.put(raw)

    def readline(self, limit=-1):
        line = self._lines.get()
        if limit is not None and limit >= 0 and len(line) > limit:
            head = line[:limit]
            self._lines.put(line[limit:])
            return head
        return line


class Outbound:
    def __init__(self):
        self._chunks = []
        self._condition = threading.Condition()

    def write(self, chunk):
        with self._condition:
            self._chunks.append(bytes(chunk))
            self._condition.notify_all()
        return len(chunk)

    def flush(self):
        pass

    def chunks(self):
        with self._condition:
            return list(self._chunks)

    def wait_messages(self, count):
        with self._condition:
            assert self._condition.wait_for(
                lambda: len(self._chunks) >= count, timeout=1.0)
            chunks = list(self._chunks)
        return [json.loads(chunk.decode("utf-8")) for chunk in chunks]


class PartialOutbound(Outbound):
    def write(self, chunk):
        super().write(chunk[:3])
        return 3


def make_transport(**kwargs):
    incoming, outgoing = Inbound(), Outbound()
    transport = ClaudeSessionTransport(
        incoming=incoming, outgoing=outgoing, default_timeout=0.2, **kwargs)
    return transport, incoming, outgoing


def test_rejects_control_response_for_unseen_request_id():
    transport, _incoming, _outgoing = make_transport()
    forged = ClaudeControlRequest(
        "forged-req", "can_use_tool", {"subtype": "can_use_tool"}, {})

    with pytest.raises(ClaudeSessionTransportError) as caught:
        transport.send_permission_decision(
            forged, ClaudePermissionDecision.allow({"command": "git status"}))

    assert caught.value.code == "control_request_not_pending"


def test_duplicate_control_request_id_is_fatal_before_any_decision():
    transport, incoming, _outgoing = make_transport()
    request = {
        "type": "control_request",
        "request_id": "req-dup",
        "request": {"subtype": "can_use_tool", "tool_name": "Bash", "input": {}},
    }
    incoming.push(request)
    incoming.push(request)

    first = transport.pop_control_request(timeout=1.0)
    protocol = transport.pop_protocol_event(timeout=1.0)

    assert first is not None
    assert protocol is not None
    assert protocol.kind == "duplicate_control_request"
    assert transport.needs_recovery() is True


def test_fatal_state_closes_control_response_writes():
    transport, incoming, _outgoing = make_transport()
    incoming.push_raw(b"{not-json}\n")
    assert transport.pop_protocol_event(timeout=1.0).kind == "malformed_json"
    request = ClaudeControlRequest(
        "req-after-fatal", "can_use_tool", {"subtype": "can_use_tool"}, {})

    with pytest.raises(ClaudeSessionTransportError) as caught:
        transport.send_permission_decision(
            request, ClaudePermissionDecision.allow({"command": "git status"}))

    assert caught.value.code == "transport_recovery_needed"


def test_invalid_json_constants_are_rejected_inbound_and_outbound():
    transport, incoming, _outgoing = make_transport()
    incoming.push_raw(b'{"type":"assistant","score":NaN}\n')

    assert transport.pop_protocol_event(timeout=1.0).kind == "malformed_json"

    transport, incoming, outgoing = make_transport()
    incoming.push({
        "type": "control_request",
        "request_id": "req-nan",
        "request": {"subtype": "can_use_tool", "tool_name": "Bash", "input": {}},
    })
    request = transport.pop_control_request(timeout=1.0)

    with pytest.raises(ClaudeSessionTransportError) as caught:
        transport.send_permission_decision(
            request, ClaudePermissionDecision.allow({"threshold": math.nan}))
    assert caught.value.code == "invalid_json_frame"
    assert b"NaN" not in b"".join(outgoing.chunks())


def test_partial_write_marks_recovery_and_does_not_accept_pending_turn():
    incoming = Inbound()
    outgoing = PartialOutbound()
    transport = ClaudeSessionTransport(
        incoming=incoming, outgoing=outgoing, default_timeout=0.2)

    with pytest.raises(ClaudeSessionTransportError) as caught:
        transport.send_user_message("partial write")

    assert caught.value.code == "write_failed"
    assert transport.needs_recovery() is True


def test_malformed_result_does_not_clear_single_pending_input():
    transport, incoming, _outgoing = make_transport()
    transport.send_user_message("first")
    incoming.push({"type": "result"})

    assert transport.pop_protocol_event(timeout=1.0).kind == "malformed_result"
    with pytest.raises(ClaudeSessionTransportError):
        transport.send_user_message("second")


def test_bool_bounds_are_rejected_not_treated_as_one():
    incoming, outgoing = Inbound(), Outbound()

    with pytest.raises(ClaudeSessionTransportError) as caught:
        ClaudeSessionTransport(
            incoming=incoming, outgoing=outgoing, max_line_bytes=True)

    assert caught.value.code == "invalid_queue_size"

def test_json_numeric_overflow_is_rejected_in_ordinary_event():
    transport, incoming, _outgoing = make_transport()
    incoming.push_raw(b'{"type":"assistant","score":1e999}\n')

    protocol = transport.pop_protocol_event(timeout=1.0)

    assert protocol is not None
    assert protocol.kind == "malformed_json"
    assert transport.pop_event(timeout=0.1) is None
    assert transport.needs_recovery() is True


def test_result_numeric_overflow_does_not_clear_pending_turn():
    transport, incoming, _outgoing = make_transport()
    transport.send_user_message("first")
    incoming.push_raw(
        b'{"type":"result","subtype":"success","duration_ms":1e999,'
        b'"duration_api_ms":1,"is_error":false,"num_turns":1,"session_id":"s1"}\n')

    protocol = transport.pop_protocol_event(timeout=1.0)

    assert protocol is not None
    assert protocol.kind == "malformed_json"
    with pytest.raises(ClaudeSessionTransportError) as caught:
        transport.send_user_message("second")
    assert caught.value.code == "transport_recovery_needed"


def test_result_validation_rejects_nonfinite_required_numbers():
    base = {
        "type": "result",
        "subtype": "success",
        "duration_ms": 1,
        "duration_api_ms": 1,
        "is_error": False,
        "num_turns": 1,
        "session_id": "s1",
    }

    assert validate_result_frame({**base, "duration_ms": math.inf}) is False
    assert validate_result_frame({**base, "duration_api_ms": math.inf}) is False


def test_unresolved_control_request_blocks_new_user_message():
    transport, incoming, outgoing = make_transport()
    incoming.push({
        "type": "control_request",
        "request_id": "req-open",
        "request": {"subtype": "can_use_tool", "tool_name": "Bash", "input": {}},
    })

    assert transport.pop_control_request(timeout=1.0).request_id == "req-open"
    with pytest.raises(ClaudeSessionTransportError) as caught:
        transport.send_user_message("must not send")

    assert caught.value.code == "pending_control_request"
    assert outgoing.chunks() == []
    assert transport.needs_recovery() is True


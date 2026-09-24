import json
import queue
import threading
import time

import pytest

from harness.claude_session_contract import ClaudePermissionDecision
from harness.claude_session_transport import ClaudeSessionTransport, ClaudeSessionTransportError


class Inbound:
    def __init__(self):
        self._lines = queue.Queue()
        self.closed = False

    def push(self, message):
        raw = json.dumps(message, separators=(",", ":")).encode("utf-8")
        self._lines.put(raw + b"\n")

    def readline(self, limit=-1):
        return self._lines.get()

    def close(self):
        self.closed = True
        self._lines.put(b"")


class GateOutbound:
    def __init__(self, *, fail_on_close=True):
        self.started = threading.Event()
        self.release = threading.Event()
        self.chunks = []
        self.closed = False
        self.fail_on_close = fail_on_close

    def write(self, chunk):
        self.started.set()
        assert self.release.wait(timeout=1.0)
        if self.closed and self.fail_on_close:
            raise OSError("closed")
        self.chunks.append(bytes(chunk))
        return len(chunk)

    def flush(self):
        pass

    def close(self):
        self.closed = True

    def messages(self):
        return [json.loads(chunk.decode("utf-8")) for chunk in self.chunks]


def make_transport():
    incoming, outgoing = Inbound(), GateOutbound()
    transport = ClaudeSessionTransport(
        incoming=incoming, outgoing=outgoing, default_timeout=0.05)
    return transport, incoming, outgoing


def test_shutdown_blocks_user_message_queued_behind_write_lock():
    transport, _incoming, outgoing = make_transport()
    transport._write_lock.acquire()
    errors = []
    done = threading.Event()
    thread = threading.Thread(target=lambda: _send_text(transport, errors, done))
    thread.start()
    time.sleep(0.05)

    assert transport.shutdown(timeout=0.05) is False
    transport._write_lock.release()
    done.wait(timeout=1.0)

    assert [error.code for error in errors] == ["transport_recovery_needed"]
    assert outgoing.chunks == []
    assert transport.needs_recovery() is True


def test_shutdown_blocks_permission_response_queued_behind_write_lock_without_resolving():
    transport, incoming, outgoing = make_transport()
    incoming.push({
        "type": "control_request",
        "request_id": "req-race",
        "request": {"subtype": "can_use_tool", "tool_name": "Bash", "input": {}},
    })
    request = transport.pop_control_request(timeout=1.0)
    assert request is not None
    transport._write_lock.acquire()
    errors = []
    done = threading.Event()
    thread = threading.Thread(target=lambda: _send_permission(
        transport, request, errors, done))
    thread.start()
    time.sleep(0.05)

    assert transport.shutdown(timeout=0.05) is False
    transport._write_lock.release()
    done.wait(timeout=1.0)

    assert [error.code for error in errors] == ["transport_recovery_needed"]
    assert outgoing.chunks == []
    assert request.request_id in transport._pending_control_tokens
    assert request.request_id not in transport._resolved_control_ids


def test_already_in_flight_permission_write_is_explicitly_uncertain_not_resolved():
    incoming, outgoing = Inbound(), GateOutbound(fail_on_close=False)
    transport = ClaudeSessionTransport(incoming=incoming, outgoing=outgoing, default_timeout=0.05)
    incoming.push({
        "type": "control_request",
        "request_id": "req-flight",
        "request": {"subtype": "can_use_tool", "tool_name": "Bash", "input": {}},
    })
    request = transport.pop_control_request(timeout=1.0)
    errors = []
    done = threading.Event()
    thread = threading.Thread(target=lambda: _send_permission(
        transport, request, errors, done))
    thread.start()
    assert outgoing.started.wait(timeout=1.0)

    assert transport.shutdown(timeout=0.05) is False
    outgoing.release.set()
    done.wait(timeout=1.0)

    assert [error.code for error in errors] == ["response_write_uncertain"]
    assert outgoing.messages()[0]["response"]["request_id"] == "req-flight"
    assert request.request_id in transport._pending_control_tokens
    assert request.request_id not in transport._resolved_control_ids


def _send_text(transport, errors, done):
    try:
        transport.send_user_message("should not write")
    except ClaudeSessionTransportError as exc:
        errors.append(exc)
    finally:
        done.set()


def _send_permission(transport, request, errors, done):
    try:
        transport.send_permission_decision(
            request, ClaudePermissionDecision.allow({"command": "git status"}))
    except ClaudeSessionTransportError as exc:
        errors.append(exc)
    finally:
        done.set()

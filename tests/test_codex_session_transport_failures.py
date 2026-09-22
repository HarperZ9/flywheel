import json
import queue
import threading

import pytest

from harness.codex_session_transport import (
    CodexSessionTransport,
    CodexSessionTransportError,
)


class Inbound:
    def __init__(self):
        self._lines = queue.Queue()

    def push_raw(self, raw):
        self._lines.put(raw)

    def push(self, message):
        self.push_raw(
            json.dumps(message, separators=(",", ":")).encode() + b"\n")

    def close(self):
        self._lines.put(b"")

    def readline(self):
        return self._lines.get()


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

    def wait_count(self, count):
        with self._condition:
            assert self._condition.wait_for(
                lambda: len(self._chunks) >= count, timeout=1.0)
        return len(self._chunks)

    def messages(self):
        with self._condition:
            chunks = list(self._chunks)
        return [json.loads(chunk.decode("utf-8")) for chunk in chunks]


class FailingOutbound(Outbound):
    def write(self, chunk):
        raise OSError("bad sk-SECRET write failure")


def make_transport(**kwargs):
    incoming, outgoing = Inbound(), Outbound()
    transport = CodexSessionTransport(
        outgoing, incoming, default_timeout=0.05, **kwargs)
    return transport, incoming, outgoing


def test_failed_write_removes_pending_request_and_redacts_provider_text():
    incoming = Inbound()
    transport = CodexSessionTransport(
        FailingOutbound(), incoming, default_timeout=0.05)

    with pytest.raises(CodexSessionTransportError) as caught:
        transport.request("thread/list", {}, timeout=0.05)

    assert caught.value.code == "write_failed"
    assert "SECRET" not in str(caught.value)
    event = transport.pop_protocol_event(timeout=1.0)
    assert event is not None
    assert event.kind == "write_failed"
    assert transport.closed is True
    incoming.push({"id": 0, "result": {"late": True}})
    event = transport.pop_protocol_event(timeout=1.0)
    assert event is not None
    assert event.kind == "eof"


def test_malformed_frame_closes_transport_with_explicit_failure_event():
    transport, incoming, _outgoing = make_transport()

    incoming.push_raw(b"{not-json\n")

    event = transport.pop_protocol_event(timeout=1.0)
    assert event is not None
    assert event.kind == "malformed_frame"
    with pytest.raises(CodexSessionTransportError) as caught:
        transport.request("thread/list", {}, timeout=0.05)
    assert caught.value.code == "malformed_frame"


def test_eof_closes_transport_and_wakes_later_requests():
    transport, incoming, _outgoing = make_transport()

    incoming.close()

    event = transport.pop_protocol_event(timeout=1.0)
    assert event is not None
    assert event.kind == "eof"
    with pytest.raises(CodexSessionTransportError) as caught:
        transport.request("thread/list", {}, timeout=0.05)
    assert caught.value.code == "eof"


def test_request_timeout_is_reported_and_late_response_is_not_silent():
    transport, incoming, outgoing = make_transport()

    with pytest.raises(CodexSessionTransportError) as caught:
        transport.request("thread/read", {"threadId": "t1"}, timeout=0.01)
    assert caught.value.code == "timeout"
    request_id = outgoing.messages()[0]["id"]
    incoming.push({"id": request_id, "result": {"late": True}})

    event = transport.pop_protocol_event(timeout=1.0)
    assert event is not None
    assert event.kind == "orphan_response"
    assert event.request_id == request_id


def test_close_wakes_pending_request_with_closed_error():
    transport, _incoming, outgoing = make_transport()
    errors = []

    thread = threading.Thread(target=lambda: errors.append(
        pytest.raises(CodexSessionTransportError,
                      transport.request, "thread/list", {}, timeout=1.0)))
    thread.start()
    outgoing.wait_count(1)
    transport.close()
    thread.join(timeout=1.0)

    assert len(errors) == 1
    assert errors[0].value.code == "closed"

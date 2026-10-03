import json
import queue
import threading
import time

import pytest

from harness.codex_session_transport import (
    CodexSessionTransport,
    CodexSessionTransportError,
)


class Inbound:
    def __init__(self):
        self._lines = queue.Queue()
        self.closed = False

    def push(self, message):
        raw = json.dumps(message, separators=(",", ":")).encode() + b"\n"
        self._lines.put(raw)

    def push_raw(self, raw):
        self._lines.put(raw)

    def close(self):
        self.closed = True
        self._lines.put(b"")

    def readline(self, size=-1):
        line = self._lines.get()
        return line if size is None or size < 0 else line[:size]


class RecordingOutbound:
    def __init__(self, returns):
        self.returns = list(returns)
        self.chunks = []
        self.closed = False

    def write(self, chunk):
        value = self.returns.pop(0)
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            self.chunks.append(bytes(chunk[:value]))
        return value

    def flush(self):
        pass

    def close(self):
        self.closed = True

    def raw(self):
        return b"".join(self.chunks)

    def messages(self):
        return [json.loads(self.raw().decode("utf-8"))]


class BlockingOutbound:
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.closed = False
        self.chunks = []

    def write(self, chunk):
        self.started.set()
        self.release.wait()
        if self.closed:
            raise OSError("stream closed")
        self.chunks.append(bytes(chunk))
        return len(chunk)

    def flush(self):
        pass

    def close(self):
        self.closed = True


def make_transport(outgoing, incoming=None, **kwargs):
    incoming = incoming or Inbound()
    return CodexSessionTransport(
        outgoing, incoming, default_timeout=0.05, **kwargs), incoming, outgoing


def queued_request(transport, incoming):
    incoming.push({"id": "approval-1", "method": "item/fileChange/requestApproval"})
    request = transport.pop_server_request(timeout=1.0)
    assert request is not None
    return request


def test_write_all_retries_positive_short_writes_until_frame_complete():
    outgoing = RecordingOutbound([1] * 100)
    transport, _incoming, outgoing = make_transport(outgoing)

    transport.notify("initialized")

    assert outgoing.messages() == [{"method": "initialized"}]
    assert transport.closed is False


@pytest.mark.parametrize("bad_return", [0, None, True])
def test_write_contract_rejects_non_positive_none_and_bool_returns(bad_return):
    outgoing = RecordingOutbound([bad_return])
    transport, _incoming, _outgoing = make_transport(outgoing)

    with pytest.raises(CodexSessionTransportError) as caught:
        transport.notify("initialized")

    assert caught.value.code == "write_failed"
    assert transport.closed is True
    event = transport.pop_protocol_event(timeout=1.0)
    assert event is not None
    assert event.kind == "write_failed"


def test_partial_write_failure_closes_transport_and_does_not_resolve_approval():
    outgoing = RecordingOutbound([1, 0])
    transport, incoming, outgoing = make_transport(outgoing)
    request = queued_request(transport, incoming)

    with pytest.raises(CodexSessionTransportError) as caught:
        transport.reply(request, result={"decision": "accept"})

    assert caught.value.code == "write_failed"
    assert request._resolved is False
    assert transport.closed is True
    assert outgoing.raw() == b"{"
    with pytest.raises(CodexSessionTransportError):
        transport.reply(request, result={"decision": "decline"})


def test_close_returns_cleanup_incomplete_when_writer_stays_blocked_until_released():
    incoming, outgoing = Inbound(), BlockingOutbound()
    transport = CodexSessionTransport(
        outgoing, incoming, default_timeout=0.05, close_timeout=0.05)
    request = queued_request(transport, incoming)
    reply_error = []
    reply_done = threading.Event()
    close_result = []

    threading.Thread(target=lambda: _capture_reply(
        transport, request, reply_error, reply_done)).start()
    assert outgoing.started.wait(timeout=1.0)
    closer = threading.Thread(target=lambda: close_result.append(transport.close()))
    closer.start()
    closer.join(timeout=1.0)

    try:
        assert close_result == [False]
        assert outgoing.closed is True
        events = []
        for _ in range(3):
            event = transport.pop_protocol_event(timeout=1.0)
            if event is not None:
                events.append(event.kind)
            if "cleanup_incomplete" in events:
                break
        assert "cleanup_incomplete" in events
    finally:
        outgoing.release.set()
    assert reply_done.wait(timeout=1.0)
    assert reply_error and reply_error[0].code == "write_failed"
    assert request._resolved is False
    assert transport.wait_closed(timeout=1.0) is True


def test_close_after_reader_failure_still_runs_stream_cleanup():
    incoming, outgoing = Inbound(), RecordingOutbound([1] * 20)
    transport = CodexSessionTransport(outgoing, incoming, default_timeout=0.05)

    incoming.push_raw(b"{not-json\n")
    event = transport.pop_protocol_event(timeout=1.0)
    assert event is not None
    assert event.kind == "malformed_frame"

    assert transport.close() is True
    assert incoming.closed is True
    assert outgoing.closed is True


def _capture_reply(transport, request, errors, done):
    try:
        transport.reply(request, result={"decision": "accept"})
    except CodexSessionTransportError as exc:
        errors.append(exc)
    finally:
        done.set()

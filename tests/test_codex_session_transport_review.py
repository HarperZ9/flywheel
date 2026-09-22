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
        self.closed = False

    def push(self, message):
        self.push_raw(json.dumps(message, separators=(",", ":")).encode() + b"\n")

    def push_raw(self, raw):
        self._lines.put(raw)

    def close(self):
        self.closed = True
        self._lines.put(b"")

    def readline(self):
        return self._lines.get()


class Outbound:
    def __init__(self):
        self._chunks = []
        self._condition = threading.Condition()
        self.closed = False

    def write(self, chunk):
        with self._condition:
            self._chunks.append(bytes(chunk))
            self._condition.notify_all()
        return len(chunk)

    def flush(self):
        pass

    def close(self):
        self.closed = True

    def messages(self):
        with self._condition:
            chunks = list(self._chunks)
        return [json.loads(chunk.decode("utf-8")) for chunk in chunks]

    def wait_messages(self, count):
        with self._condition:
            assert self._condition.wait_for(lambda: len(self._chunks) >= count, 1.0)
        return self.messages()


class BlockingOutbound(Outbound):
    def __init__(self):
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()

    def write(self, chunk):
        self.started.set()
        assert self.release.wait(timeout=1.0)
        return super().write(chunk)


class SizedReadlineInbound:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def readline(self, size=-1):
        self.calls.append(size)
        return self.payload if size is None or size < 0 else self.payload[:size]

    def close(self):
        pass


def make_transport(incoming=None, outgoing=None, **kwargs):
    incoming = incoming or Inbound()
    outgoing = outgoing or Outbound()
    transport = CodexSessionTransport(outgoing, incoming, default_timeout=0.05, **kwargs)
    return transport, incoming, outgoing


def queued_request(transport, incoming):
    incoming.push({"id": "approval-1", "method": "item/fileChange/requestApproval"})
    request = transport.pop_server_request(timeout=1.0)
    assert request is not None
    return request



def test_close_closes_streams_and_reader_can_be_joined():
    transport, incoming, outgoing = make_transport()

    transport.close()

    assert incoming.closed is True
    assert outgoing.closed is True
    assert transport.wait_closed(timeout=1.0) is True


def test_inbound_non_finite_response_is_malformed():
    transport, incoming, outgoing = make_transport()
    errors = []
    thread = threading.Thread(target=lambda: errors.append(pytest.raises(
        CodexSessionTransportError, transport.request, "thread/list", {}, timeout=1.0)))
    thread.start()
    assert outgoing.wait_messages(1)[0]["id"] == 0

    incoming.push_raw(b'{"id":0,"result":{"x":NaN}}\n')

    event = transport.pop_protocol_event(timeout=1.0)
    thread.join(timeout=1.0)
    assert event is not None
    assert event.kind == "malformed_frame"
    assert errors[0].value.code == "malformed_frame"


def test_inbound_non_finite_notification_and_server_request_are_malformed():
    transport, incoming, _outgoing = make_transport()

    incoming.push_raw(b'{"method":"thread/started","params":{"x":Infinity}}\n')

    event = transport.pop_protocol_event(timeout=1.0)
    assert event is not None
    assert event.kind == "malformed_frame"
    assert transport.pop_notification(timeout=0.01) is None

    transport, incoming, _outgoing = make_transport()
    incoming.push_raw(
        b'{"id":"approval-1","method":"item/fileChange/requestApproval",'
        b'"params":{"x":-Infinity}}\n')

    event = transport.pop_protocol_event(timeout=1.0)
    assert event is not None
    assert event.kind == "malformed_frame"
    assert transport.pop_server_request(timeout=0.01) is None


def test_reply_serialization_failure_does_not_consume_server_request():
    transport, incoming, outgoing = make_transport()
    request = queued_request(transport, incoming)

    with pytest.raises(CodexSessionTransportError) as caught:
        transport.reply(request, result={"x": float("nan")})

    assert caught.value.code == "invalid_reply"
    assert request._resolved is False
    assert outgoing.messages() == []
    transport.reply(request, result={"decision": "decline"})
    assert outgoing.wait_messages(1)[0]["result"] == {"decision": "decline"}


def test_reply_error_code_bool_is_rejected_without_consuming_request():
    transport, incoming, outgoing = make_transport()
    request = queued_request(transport, incoming)

    with pytest.raises(CodexSessionTransportError) as caught:
        transport.reply(request, error={"code": True, "message": "bad"})

    assert caught.value.code == "invalid_reply"
    assert request._resolved is False
    transport.reply(request, result={"decision": "decline"})
    assert outgoing.wait_messages(1)[0]["result"] == {"decision": "decline"}


def test_event_loss_between_reply_serialization_and_commit_blocks_write(monkeypatch):
    import harness.codex_session_transport as transport_module
    transport, incoming, outgoing = make_transport()
    request = queued_request(transport, incoming)
    real_encode = transport_module.encode

    def encode_then_lose_events(message):
        data = real_encode(message)
        transport._event_loss = True
        return data

    monkeypatch.setattr(transport_module, "encode", encode_then_lose_events)

    with pytest.raises(CodexSessionTransportError) as caught:
        transport.reply(request, result={"decision": "accept"})

    assert caught.value.code == "event_loss"
    assert request._resolved is False
    assert outgoing.messages() == []


def test_reader_uses_bounded_readline_before_buffering_oversize_frame():
    incoming = SizedReadlineInbound(b'{"method":"x","params":"too-large"}\n')
    transport, _incoming, _outgoing = make_transport(
        incoming=incoming, max_frame_bytes=8)

    event = transport.pop_protocol_event(timeout=1.0)

    assert incoming.calls[0] == 9
    assert event is not None
    assert event.kind == "frame_too_large"

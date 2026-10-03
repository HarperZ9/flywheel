import json
import queue
import threading

import pytest

from harness.codex_session_transport import (
    CodexServerRequest,
    CodexSessionTransport,
    CodexSessionTransportError,
)


class Inbound:
    def __init__(self):
        self._lines = queue.Queue()

    def push(self, message):
        raw = json.dumps(message, separators=(",", ":")).encode("utf-8")
        self._lines.put(raw + b"\n")

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

    def messages(self):
        with self._condition:
            chunks = list(self._chunks)
        return [json.loads(chunk.decode("utf-8")) for chunk in chunks]

    def wait_messages(self, count):
        with self._condition:
            assert self._condition.wait_for(
                lambda: len(self._chunks) >= count, timeout=1.0)
        return self.messages()


def make_transport(**kwargs):
    incoming, outgoing = Inbound(), Outbound()
    transport = CodexSessionTransport(
        outgoing, incoming, default_timeout=0.2, **kwargs)
    return transport, incoming, outgoing


def test_forged_server_request_reply_cannot_reuse_pending_id():
    transport, incoming, outgoing = make_transport()
    incoming.push({
        "id": "approval-1",
        "method": "item/fileChange/requestApproval",
        "params": {"itemId": "i1"},
    })
    real_request = transport.pop_server_request(timeout=1.0)
    forged = CodexServerRequest(
        "approval-1", "item/fileChange/requestApproval", {}, 1, transport)

    with pytest.raises(CodexSessionTransportError) as caught:
        transport.reply(forged, result={"decision": "accept"})
    assert caught.value.code == "request_not_pending"
    assert outgoing.messages() == []

    transport.reply(real_request, result={"decision": "decline"})
    assert outgoing.wait_messages(1)[0]["result"] == {"decision": "decline"}


def test_duplicate_server_request_id_invalidates_pending_approval_decisions():
    transport, incoming, outgoing = make_transport(server_request_queue_size=2)
    incoming.push({
        "id": "approval-1",
        "method": "item/fileChange/requestApproval",
        "params": {"itemId": "i1"},
    })
    first = transport.pop_server_request(timeout=1.0)
    incoming.push({
        "id": "approval-1",
        "method": "item/fileChange/requestApproval",
        "params": {"itemId": "i2"},
    })

    event = transport.pop_protocol_event(timeout=1.0)
    assert event is not None
    assert event.kind == "duplicate_server_request"
    refusal = outgoing.wait_messages(1)[0]
    assert refusal["id"] == "approval-1"
    assert refusal["error"]["code"] == -32000
    with pytest.raises(CodexSessionTransportError) as caught:
        transport.reply(first, result={"decision": "accept"})
    assert caught.value.code == "server_requests_invalidated"
    assert len(outgoing.messages()) == 1


def test_server_request_overflow_is_reported_and_invalidates_queued_approval():
    transport, incoming, outgoing = make_transport(server_request_queue_size=1)
    incoming.push({
        "id": "approval-1",
        "method": "item/fileChange/requestApproval",
        "params": {"itemId": "i1"},
    })
    incoming.push({
        "id": "approval-2",
        "method": "item/fileChange/requestApproval",
        "params": {"itemId": "i2"},
    })

    queued = transport.pop_server_request(timeout=1.0)
    assert queued.id == "approval-1"
    event = transport.pop_protocol_event(timeout=1.0)
    assert event is not None
    assert event.kind == "server_request_overflow"
    assert transport.server_request_overflowed() is True
    refusal = outgoing.wait_messages(1)[0]
    assert refusal["id"] == "approval-2"
    assert refusal["error"]["code"] == -32000
    assert "overflow" in refusal["error"]["message"]
    with pytest.raises(CodexSessionTransportError) as caught:
        transport.reply(queued, result={"decision": "accept"})
    assert caught.value.code == "server_requests_invalidated"


def test_notification_overflow_blocks_pending_server_request_reply():
    transport, incoming, outgoing = make_transport(notification_queue_size=1)
    incoming.push({
        "id": "approval-1",
        "method": "item/fileChange/requestApproval",
        "params": {"itemId": "i1"},
    })
    request = transport.pop_server_request(timeout=1.0)
    incoming.push({"method": "thread/started", "params": {"threadId": "t1"}})
    incoming.push({"method": "turn/started", "params": {"turnId": "u1"}})

    event = transport.pop_protocol_event(timeout=1.0)
    assert event is not None
    assert event.kind == "notification_overflow"
    with pytest.raises(CodexSessionTransportError) as caught:
        transport.reply(request, result={"decision": "accept"})
    assert caught.value.code == "event_loss"
    assert outgoing.messages() == []


def test_close_blocks_notifications_and_server_request_replies_without_write():
    transport, incoming, outgoing = make_transport()
    incoming.push({
        "id": "approval-1",
        "method": "item/fileChange/requestApproval",
        "params": {"itemId": "i1"},
    })
    request = transport.pop_server_request(timeout=1.0)
    transport.close()

    with pytest.raises(CodexSessionTransportError) as caught:
        transport.notify("initialized")
    assert caught.value.code == "closed"
    with pytest.raises(CodexSessionTransportError) as caught:
        transport.reply(request, result={"decision": "decline"})
    assert caught.value.code == "closed"
    assert outgoing.messages() == []

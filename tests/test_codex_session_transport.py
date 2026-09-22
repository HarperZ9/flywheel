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

    def push(self, message):
        raw = json.dumps(message, separators=(",", ":")).encode("utf-8")
        self._lines.put(raw + b"\n")

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

    def messages(self):
        with self._condition:
            chunks = list(self._chunks)
        return [json.loads(chunk.decode("utf-8")) for chunk in chunks]

    def wait_messages(self, count):
        with self._condition:
            assert self._condition.wait_for(
                lambda: len(self._chunks) >= count, timeout=1.0)
        return self.messages()


class BlockingOutbound(Outbound):
    def __init__(self):
        super().__init__()
        self.release = threading.Event()

    def write(self, chunk):
        self.release.wait(timeout=1.0)
        return super().write(chunk)


def make_transport(**kwargs):
    incoming, outgoing = Inbound(), Outbound()
    transport = CodexSessionTransport(
        outgoing, incoming, default_timeout=0.2, **kwargs)
    return transport, incoming, outgoing


def test_official_codex_frames_do_not_require_or_emit_jsonrpc_member():
    transport, incoming, outgoing = make_transport()
    result = []

    thread = threading.Thread(target=lambda: result.append(
        transport.request("initialize", {"clientInfo": {"name": "flywheel"}},
                          timeout=1.0)))
    thread.start()
    sent = outgoing.wait_messages(1)[0]
    assert sent == {
        "id": 0,
        "method": "initialize",
        "params": {"clientInfo": {"name": "flywheel"}},
    }
    assert "jsonrpc" not in sent

    incoming.push({"id": 0, "result": {"userAgent": "codex-cli/0.144.6"}})
    thread.join(timeout=1.0)
    assert result == [{"userAgent": "codex-cli/0.144.6"}]


def test_concurrent_requests_receive_out_of_order_responses_by_id():
    transport, incoming, outgoing = make_transport()
    results, errors = {}, []

    def call(method):
        try:
            results[method] = transport.request(method, {}, timeout=1.0)
        except Exception as exc:  # pragma: no cover - asserted by errors
            errors.append(exc)

    threads = [
        threading.Thread(target=call, args=("thread/list",)),
        threading.Thread(target=call, args=("model/list",)),
    ]
    for thread in threads:
        thread.start()
    sent = outgoing.wait_messages(2)
    assert all("jsonrpc" not in message for message in sent)
    ids = {message["method"]: message["id"] for message in sent}

    incoming.push({"id": ids["model/list"], "result": {"models": ["b"]}})
    incoming.push({"id": ids["thread/list"], "result": {"threads": ["a"]}})
    for thread in threads:
        thread.join(timeout=1.0)

    assert errors == []
    assert results == {
        "thread/list": {"threads": ["a"]},
        "model/list": {"models": ["b"]},
    }



def test_bool_response_id_is_malformed_not_alias_for_integer_id():
    transport, incoming, outgoing = make_transport()
    results, errors = [], []

    def call():
        try:
            results.append(transport.request("thread/list", {}, timeout=1.0))
        except CodexSessionTransportError as exc:
            errors.append(exc)

    thread = threading.Thread(target=call)
    thread.start()
    assert outgoing.wait_messages(1)[0]["id"] == 0
    incoming.push({"id": False, "result": {"wrong": True}})

    event = transport.pop_protocol_event(timeout=1.0)
    thread.join(timeout=1.0)
    assert event is not None
    assert event.kind == "malformed_frame"
    assert results == []
    assert [error.code for error in errors] == ["malformed_frame"]


def test_duplicate_response_does_not_replace_first_settled_response():
    transport, _incoming, _outgoing = make_transport()
    request_id = transport._reserve("thread/list")

    transport._settle({"id": request_id, "result": {"models": ["first"]}})
    transport._settle({"id": request_id, "result": {"models": ["second"]}})

    event = transport.pop_protocol_event(timeout=1.0)
    assert event is not None
    assert event.kind == "duplicate_response"
    assert event.request_id == request_id
    assert transport._wait("thread/list", request_id, 0.01) == {
        "models": ["first"]
    }


def test_server_request_with_same_id_as_client_request_is_not_a_response():
    transport, incoming, outgoing = make_transport()
    result = []

    thread = threading.Thread(target=lambda: result.append(
        transport.request("thread/start", {}, timeout=1.0)))
    thread.start()
    request_id = outgoing.wait_messages(1)[0]["id"]
    incoming.push({
        "id": request_id,
        "method": "item/permissions/requestApproval",
        "params": {"scope": "workspace-write"},
    })

    server_request = transport.pop_server_request(timeout=1.0)
    assert server_request is not None
    assert server_request.id == request_id
    assert server_request.method == "item/permissions/requestApproval"
    assert result == []

    incoming.push({"id": request_id, "result": {"threadId": "t1"}})
    thread.join(timeout=1.0)
    assert result == [{"threadId": "t1"}]


def test_notifications_are_bounded_and_loss_is_reported():
    transport, incoming, _outgoing = make_transport(notification_queue_size=1)

    incoming.push({"method": "thread/started", "params": {"threadId": "t1"}})
    incoming.push({
        "method": "turn/started",
        "params": {"threadId": "t1", "turnId": "u1"},
    })

    note = transport.pop_notification(timeout=1.0)
    assert note is not None
    assert note.sequence == 1
    assert note.method == "thread/started"
    assert note.params == {"threadId": "t1"}
    event = transport.pop_protocol_event(timeout=1.0)
    assert event is not None
    assert event.kind == "notification_overflow"
    assert transport.notification_overflowed() is True


def test_server_requests_require_one_use_explicit_reply():
    transport, incoming, outgoing = make_transport()
    incoming.push({
        "id": "approval-1",
        "method": "item/commandExecution/requestApproval",
        "params": {"itemId": "i1"},
    })
    request = transport.pop_server_request(timeout=1.0)

    transport.reply(request, result={"decision": "decline"})

    assert outgoing.wait_messages(1) == [{
        "id": "approval-1",
        "result": {"decision": "decline"},
    }]
    with pytest.raises(CodexSessionTransportError) as caught:
        transport.reply(request, result={"decision": "accept"})
    assert caught.value.code == "request_resolved"
    assert len(outgoing.messages()) == 1

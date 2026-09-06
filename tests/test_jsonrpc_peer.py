"""The peer both protocols stand on, driven from the far end of a real pipe.

Everything here was reachable only through ACP or LSP before, which meant the
shared spine was tested twice in the ways those two bindings happen to use it
and not at all in the ways they do not. A request answered out of order, a call
abandoned at its timeout, a stream that ends while somebody is waiting, and a
handler that calls back while it is answering are all peer behaviour, and a bug
in any of them is a bug in both protocols at once.

Framing is LspFraming on both sides here, which would be circular if this file
were testing framing. It is not: tests/test_lsp_wire.py pins the byte format
against a hand-written server, and this file only needs some framing to exist so
messages can cross.
"""
import os
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from harness.jsonrpc import (METHOD_NOT_FOUND, notification, request, success)
from harness.jsonrpc_peer import (RECEIVED, SENT, ConnectionClosed, Peer,
                                  PeerError, RejectAll)
from harness.lsp_wire import LspFraming


class Far:
    """The other end of the pipe, driven a message at a time from the test."""

    def __init__(self, outgoing, incoming) -> None:
        self._out, self._in = outgoing, incoming
        self._framing = LspFraming()
        self._waiting: list[dict] = []

    def read(self) -> dict:
        while not self._waiting:
            frame = self._framing.read(self._in)
            if frame is None:
                raise AssertionError("the peer closed the stream")
            self._waiting.extend(frame.messages)
        return self._waiting.pop(0)

    def send(self, message: dict) -> None:
        self._out.write(self._framing.encode(message))
        self._out.flush()


def error(request_id, code, message, data=None) -> dict:
    return {"jsonrpc": "2.0", "id": request_id,
            "error": {"code": code, "message": message, "data": data}}


@pytest.fixture
def link():
    """Build a started peer and the hand-driven far end of its pipes.

    Teardown ends the peer's input before closing anything, and waits for the
    reader to notice. Closing a pipe out from under a thread that is blocked
    reading it hangs on Windows rather than raising, so the order here is the
    difference between a suite that finishes and one that stops.
    """
    opened = []

    def build(handler=None, observer=None):
        near_in, far_out = os.pipe()
        far_in, near_out = os.pipe()
        streams = [os.fdopen(fd, mode, 0) for fd, mode in
                   ((near_in, "rb"), (near_out, "wb"),
                    (far_in, "rb"), (far_out, "wb"))]
        peer = Peer(streams[1], streams[0], framing=LspFraming(),
                    handler=handler, observer=observer, name="test").start()
        opened.append((peer, streams))
        return peer, Far(streams[3], streams[2]), streams[3].close

    yield build
    for peer, streams in opened:
        streams[3].close()
        deadline = time.monotonic() + 10.0
        while not peer.closed and time.monotonic() < deadline:
            time.sleep(0.005)
        peer.close()
        for stream in streams:
            try:
                stream.close()
            except OSError:
                pass


def test_two_calls_answered_out_of_order_each_get_their_own_result(link):
    # The pending table is keyed by id for exactly this. A peer that assumed
    # answers arrive in the order the requests went out would hand each caller
    # the other one's result, and both would look like plausible answers.
    peer, far, _ = link()
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(peer.call, "one", None, timeout=10)
        second = pool.submit(peer.call, "two", None, timeout=10)
        ids = {}
        for _ in range(2):
            sent = far.read()
            ids[sent["method"]] = sent["id"]
        assert ids["one"] != ids["two"]
        far.send(success(ids["two"], "second"))
        far.send(success(ids["one"], "first"))
        assert first.result(10) == "first"
        assert second.result(10) == "second"


def test_an_error_response_arrives_as_a_peer_error_carrying_its_code(link):
    peer, far, _ = link()
    with ThreadPoolExecutor(1) as pool:
        waiting = pool.submit(peer.call, "ask", None, timeout=10)
        far.send(error(far.read()["id"], -32803, "request failed", {"n": 1}))
        with pytest.raises(PeerError) as raised:
            waiting.result(10)
    # The code is the part a caller branches on, so it survives as a number
    # rather than only as text in the message.
    assert raised.value.code == -32803
    assert raised.value.data == {"n": 1}


def test_a_call_that_times_out_leaves_the_peer_usable(link):
    peer, far, _ = link()
    with pytest.raises(TimeoutError, match="slow"):
        peer.call("slow", timeout=0.2)
    # The answer the peer stopped waiting for turns up anyway. Nothing is
    # waiting on that id, and dropping it has to be quiet: a reader that raised
    # here would take the connection down over a message that arrived late.
    far.send(success(far.read()["id"], "too late"))
    with ThreadPoolExecutor(1) as pool:
        waiting = pool.submit(peer.call, "after", None, timeout=10)
        far.send(success(far.read()["id"], "answered"))
        assert waiting.result(10) == "answered"


def test_closing_hands_every_waiter_the_reason_it_was_closed(link):
    peer, far, _ = link()
    reason = ConnectionClosed("the child was killed")
    with ThreadPoolExecutor(1) as pool:
        waiting = pool.submit(peer.call, "ask", None, timeout=10)
        far.read()
        peer.close(reason)
        with pytest.raises(ConnectionClosed, match="killed"):
            waiting.result(10)
    assert peer.closed


def test_the_stream_ending_wakes_a_call_that_was_still_waiting(link):
    peer, far, end_the_stream = link()
    with ThreadPoolExecutor(1) as pool:
        waiting = pool.submit(peer.call, "ask", None, timeout=10)
        far.read()
        end_the_stream()
        with pytest.raises(ConnectionClosed):
            waiting.result(10)


def test_a_method_this_side_does_not_have_is_refused_not_ignored(link):
    peer, far, _ = link()
    far.send(request(7, "nope", {}))
    answer = far.read()
    assert answer["id"] == 7
    assert answer["error"]["code"] == METHOD_NOT_FOUND
    assert peer.handler is not None


def test_a_notification_is_acted_on_and_never_answered(link):
    handler = RejectAll()
    peer, far, _ = link(handler=handler)
    far.send(notification("note", {"n": 1}))
    far.send(request(9, "nope", {}))
    # The next thing on the wire is the refusal of request 9. Answering a
    # notification is a protocol violation, and the way it shows up is an extra
    # response the far side cannot match to anything it sent.
    assert far.read()["id"] == 9
    assert handler.seen == [("note", {"n": 1})]
    assert peer.closed is False


class Reentrant:
    """A handler that calls back into the peer before it answers."""

    def __init__(self) -> None:
        self.peer = None

    def on_request(self, method: str, params: dict) -> object:
        return {"echo": self.peer.call("ping", timeout=5)}

    def on_notification(self, method: str, params: dict) -> None:
        pass


def test_a_handler_may_call_the_peer_while_it_is_answering(link):
    # The reason requests are answered on their own thread. On the reader
    # thread this deadlocks: the handler waits for an answer that only the
    # reader can deliver, and the reader is inside the handler. It surfaces as
    # a five-second stall and then an internal error, not as a hang.
    handler = Reentrant()
    peer, far, _ = link(handler=handler)
    handler.peer = peer
    far.send(request(1, "ask", {}))
    inner = far.read()
    assert inner["method"] == "ping"
    far.send(success(inner["id"], "pong"))
    answered = far.read()
    assert answered["id"] == 1
    assert answered["result"] == {"echo": "pong"}


def test_the_observer_is_handed_both_directions_before_anything_acts(link):
    seen = []
    peer, far, _ = link(observer=lambda direction, message:
                        seen.append((direction, message.get("method"))))
    with ThreadPoolExecutor(1) as pool:
        waiting = pool.submit(peer.call, "ask", None, timeout=10)
        far.send(success(far.read()["id"], None))
        waiting.result(10)
    far.send(notification("told", {}))
    with ThreadPoolExecutor(1) as pool:
        second = pool.submit(peer.call, "again", None, timeout=10)
        far.send(success(far.read()["id"], None))
        second.result(10)
    assert (SENT, "ask") in seen
    assert (RECEIVED, None) in seen          # the response, which has no method
    assert (RECEIVED, "told") in seen

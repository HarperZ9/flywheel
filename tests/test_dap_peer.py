"""The DAP connection, driven from the far end of a real pipe.

The far end here is hand-driven rather than scripted, because the things worth
testing about a peer are the orderings a scripted adapter would never produce:
two answers that come back swapped, an answer to a request the caller already
abandoned, a reverse request answered by a handler that calls back into the peer
while it is answering, and a stream that ends with somebody waiting on it.

The one that matters most to this protocol is `send` without `await_reply`.
DAP's launch has to be in flight while configuration is still going out, so a
peer whose only verb was `call` could not speak to half the adapters in
existence. That seam is tested here rather than through the session, because the
session's ordering is only correct if this layer actually lets a request sit.
"""
import os
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from harness.dap_peer import (RECEIVED, SENT, AdapterError, CommandNotSupported,
                              ConnectionClosed, DapPeer)
from harness.dap_wire import DapFraming, error_response, event, response


class Far:
    """The adapter's end of the pipe, one message at a time."""

    def __init__(self, outgoing, incoming) -> None:
        self._out, self._in = outgoing, incoming
        self._framing = DapFraming()
        self._seq = 0

    def read(self) -> dict:
        frame = self._framing.read(self._in)
        if frame is None:
            raise AssertionError("the peer closed the stream")
        if frame.malformed:
            raise AssertionError(f"the peer wrote {frame.malformed}")
        return frame.message

    def send(self, message: dict) -> None:
        self._out.write(self._framing.encode(message))
        self._out.flush()

    def raw(self, payload: bytes) -> None:
        self._out.write(b"Content-Length: %d\r\n\r\n%b" % (len(payload), payload))
        self._out.flush()

    def next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def close(self) -> None:
        """End the adapter's side of the stream, the way a dead adapter does."""
        self._out.close()


@pytest.fixture
def link():
    """A started peer and the far end of its pipes.

    Teardown ends the peer's input before closing anything else. A pipe closed
    out from under a thread that is blocked reading it hangs on Windows rather
    than raising, which is the difference between a suite that finishes and one
    that stops here.
    """
    opened = []

    def build(handler=None, observer=None):
        near_in, far_out = os.pipe()
        far_in, near_out = os.pipe()
        streams = [os.fdopen(fd, mode, 0) for fd, mode in
                   ((near_in, "rb"), (near_out, "wb"),
                    (far_in, "rb"), (far_out, "wb"))]
        peer = DapPeer(streams[1], streams[0], framing=DapFraming(),
                       handler=handler, observer=observer, name="test").start()
        opened.append((peer, streams))
        return peer, Far(streams[3], streams[2])

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


class Handler:
    """A handler that answers, records, and can call back while answering."""

    def __init__(self, answer=None, callback=None) -> None:
        self.answer = answer if answer is not None else {"ok": True}
        self.callback = callback
        self.requests: list[tuple[str, dict]] = []
        self.events: list[tuple[str, dict]] = []

    def on_request(self, command, arguments):
        self.requests.append((command, arguments))
        if command == "unsupported":
            raise CommandNotSupported(command)
        if command == "explodes":
            raise ValueError("the handler could not answer")
        if self.callback is not None:
            self.callback()
        return self.answer

    def on_event(self, name, body):
        self.events.append((name, body))


def test_a_sent_request_can_sit_in_flight_while_others_go_out(link):
    # The DAP launch ordering rests on this. A peer whose only verb was `call`
    # would block here and never send the configuration the adapter is waiting
    # for before it answers.
    peer, far = link()
    pending = peer.send("launch", {"program": "app.py"})
    peer.send("setBreakpoints", {"source": {"path": "app.py"}})
    assert far.read()["command"] == "launch"
    second = far.read()
    assert second["command"] == "setBreakpoints"
    assert not pending.done.is_set()
    far.send(response(far.next_seq(), pending.seq, "launch", {"started": True}))
    assert peer.await_reply(pending, timeout=10) == {"started": True}


def test_two_answers_that_arrive_swapped_each_reach_their_own_caller(link):
    # Matched on request_seq. A peer that assumed answers arrive in the order
    # the requests went out would hand each caller the other one's body, and
    # both would look like plausible answers to the request that was made.
    peer, far = link()
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(peer.call, "threads", None, timeout=10)
        second = pool.submit(peer.call, "scopes", {"frameId": 1}, timeout=10)
        seqs = {}
        for _ in range(2):
            sent = far.read()
            seqs[sent["command"]] = sent["seq"]
        assert seqs["threads"] != seqs["scopes"]
        far.send(response(far.next_seq(), seqs["scopes"], "scopes", ["second"]))
        far.send(response(far.next_seq(), seqs["threads"], "threads", ["first"]))
        assert first.result(10) == ["first"]
        assert second.result(10) == ["second"]


def test_a_failed_response_raises_with_the_command_and_the_reason(link):
    peer, far = link()
    with ThreadPoolExecutor(1) as pool:
        waiting = pool.submit(peer.call, "launch", {}, timeout=10)
        sent = far.read()
        far.send(error_response(far.next_seq(), sent["seq"], "launch",
                                "the program is missing"))
        with pytest.raises(AdapterError) as raised:
            waiting.result(10)
    # Both parts are on the exception rather than only in its text, because a
    # caller deciding what to do next branches on the command.
    assert raised.value.command == "launch"
    assert raised.value.message == "the program is missing"


def test_a_reverse_request_is_answered_by_the_handler(link):
    handler = Handler(answer={"processId": 4321})
    peer, far = link(handler=handler)
    far.send({"seq": far.next_seq(), "type": "request",
              "command": "runInTerminal", "arguments": {"args": ["python"]}})
    answer = far.read()
    assert answer["success"] is True
    assert answer["body"] == {"processId": 4321}
    assert handler.requests == [("runInTerminal", {"args": ["python"]})]
    far.send(event(far.next_seq(), "terminated"))
    deadline = time.monotonic() + 10.0
    while not handler.events and time.monotonic() < deadline:
        time.sleep(0.01)
    assert handler.events == [("terminated", {})]


def test_a_refusal_is_written_back_rather_than_left_unanswered(link):
    # An adapter that gets no answer at all waits on its own request forever,
    # and the session ends looking like a hang instead of like a boundary being
    # held. The refusal is the record that the boundary was reached.
    peer, far = link(handler=Handler())
    far.send({"seq": far.next_seq(), "type": "request",
              "command": "unsupported", "arguments": {}})
    answer = far.read()
    assert answer["success"] is False
    assert "unsupported" in answer["message"]
    assert peer.closed is False


def test_a_handler_that_raises_anything_else_still_owes_an_answer(link):
    peer, far = link(handler=Handler())
    far.send({"seq": far.next_seq(), "type": "request", "command": "explodes",
              "arguments": {}})
    answer = far.read()
    assert answer["success"] is False
    assert "could not answer" in answer["message"]
    assert peer.closed is False


def test_a_handler_may_call_back_into_the_peer_while_it_answers(link):
    # Answering on the reader thread would deadlock this against its own
    # response, so reverse requests are answered on their own thread. A policy
    # that logs through the connection is the ordinary case.
    called = []

    def callback():
        called.append(peer.send("output", {"note": "starting"}).seq)

    handler = Handler(callback=callback)
    peer, far = link(handler=handler)
    far.send({"seq": far.next_seq(), "type": "request",
              "command": "runInTerminal", "arguments": {}})
    assert far.read()["command"] == "output"
    assert far.read()["success"] is True
    assert len(called) == 1


def test_an_unusable_message_is_kept_and_the_next_one_still_routes(link):
    # The length was good, so the stream is still aligned. Dropping the session
    # here would lose the rest of a debug run over one message.
    handler = Handler()
    peer, far = link(handler=handler)
    far.raw(b"{ not json at all")
    far.send(event(far.next_seq(), "terminated"))
    deadline = time.monotonic() + 10.0
    while not handler.events and time.monotonic() < deadline:
        time.sleep(0.01)
    assert handler.events == [("terminated", {})]
    assert peer.malformed and "not JSON" in peer.malformed[0]


def test_a_stream_that_ends_wakes_every_waiter_with_the_same_reason(link):
    peer, far = link()
    with ThreadPoolExecutor(1) as pool:
        waiting = pool.submit(peer.call, "threads", None, timeout=10)
        far.read()
        far.close()
        with pytest.raises(ConnectionClosed):
            waiting.result(10)


def test_a_call_that_times_out_drops_its_waiter(link):
    # Left in place, a late answer would settle a caller that is already gone
    # and the next request reusing that seq would read the stale body.
    peer, far = link()
    with pytest.raises(TimeoutError):
        peer.call("threads", None, timeout=0.1)
    sent = far.read()
    far.send(response(far.next_seq(), sent["seq"], "threads", ["late"]))
    far.send(event(far.next_seq(), "terminated"))
    assert peer.closed is False


def test_the_observer_sees_both_directions_before_anything_acts(link):
    seen = []
    peer, far = link(handler=Handler(),
                     observer=lambda direction, message: seen.append(
                         (direction, message.get("command")
                          or message.get("event"))))
    with ThreadPoolExecutor(1) as pool:
        waiting = pool.submit(peer.call, "threads", None, timeout=10)
        sent = far.read()
        far.send(response(far.next_seq(), sent["seq"], "threads", []))
        waiting.result(10)
    assert (SENT, "threads") in seen
    assert (RECEIVED, "threads") in seen

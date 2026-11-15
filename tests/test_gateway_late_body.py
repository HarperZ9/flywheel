"""A request body that arrives too late is answered 408 on every route.

Fifth review round of 2.0.0, the lead's ruling 3 (finding R11 of the fourth
review). The three model interfaces answered 408 for a body that stopped or
kept dripping past its deadline. Every other route that reads a body answered
500: the operation grant step in front of /v1/chat/completions, /api/route
and /v1/embeddings reported the timed-out read as `STORE_COMMIT_FAILED`, and
routes with no grant step fell through to the handler's "internal error".

Now `HeaderDeadline.read` raises `BodyTimeout`, which no route's own `except
Exception` can catch, and the gateway handler answers 408 and closes. Nothing
is sent upstream in any case: each route reads its body before it does
anything else.

A real gateway on a loopback port, raw sockets, a stub upstream. No provider
is called.
"""
import json
import socket
import threading
import time
from urllib.parse import urlparse

import pytest

from harness import gateway_read_timeout
from tests import gateway_messages_support as support
from tests.gateway_keys_support import keyed, served, turn2  # noqa: F401  (fixtures)

pytestmark = pytest.mark.release_gate   # run against the built wheel before a release

LIMIT = 0.5                             # the read timeout these tests set, in seconds
# Routes outside the model interfaces that read a request body. The first three sit behind
# the operation grant step; /api/agent is an operation route; /generate is proxied.
ROUTES = ["/v1/chat/completions", "/api/route", "/v1/embeddings", "/api/agent", "/generate",
          "/api/skills/install"]


def _head(path: str, length: int) -> bytes:
    return (f"POST {path} HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\n"
            f"Authorization: Bearer {support.TOKEN}\r\nContent-Length: {length}\r\n\r\n").encode()


def _exchange(url: str, path: str, drip: bool) -> tuple:
    """Promise 5000 body bytes and send none (or one every 0.2 s); (status, body, seconds)."""
    target, started = urlparse(url), time.monotonic()
    with socket.create_connection((target.hostname, target.port), timeout=30) as sock:
        sock.sendall(_head(path, 5000))

        def keep_sending():
            for _ in range(100):
                try:
                    sock.sendall(b" ")
                except OSError:
                    return
                time.sleep(0.2)
        if drip:
            threading.Thread(target=keep_sending, daemon=True).start()
        data = b""
        while True:
            try:
                more = sock.recv(65536)
            except OSError:
                break
            if not more:
                break                   # the gateway closed the connection
            data += more
    head, _, body = data.partition(b"\r\n\r\n")
    status = int(head.split(b" ", 2)[1]) if head.startswith(b"HTTP/") else 0
    return status, body, time.monotonic() - started


@pytest.mark.parametrize("drip", [True, False])
@pytest.mark.parametrize("path", ROUTES)
def test_a_late_body_outside_the_model_interfaces_is_answered_408(
        served, monkeypatch, path, drip):
    monkeypatch.setenv(gateway_read_timeout.ENV, str(LIMIT))
    url, upstream, ledger = served(turn2(1))
    status, body, took = _exchange(url, path, drip)
    assert status == 408, (path, drip, status, body[:300])
    error = json.loads(body)["error"]
    assert error["code"] == "request_timeout" and "Nothing was sent upstream" in error["message"]
    assert "STORE_COMMIT_FAILED" not in body.decode() and "internal error" not in body.decode()
    # Closed by the gateway after the deadline (four read timeouts for a dripped body, one for
    # a silent one) plus the drain of at most two seconds.
    assert took < LIMIT * gateway_read_timeout.BODY_READS + 2 + 4
    assert upstream.requests == [] and ledger.entries == []


def test_control_a_body_that_arrives_in_time_is_not_answered_408(served, monkeypatch):
    """The same route with its whole body: the route's own answer, whatever it is."""
    monkeypatch.setenv(gateway_read_timeout.ENV, str(LIMIT))
    url, _upstream, _ledger = served(turn2(1))
    target = urlparse(url)
    payload = json.dumps({"prompt": "Hi.", "endpoint": "no-such-endpoint"}).encode()
    with socket.create_connection((target.hostname, target.port), timeout=30) as sock:
        sock.sendall(_head("/api/route", len(payload)) + payload)
        data = sock.recv(65536)
    assert data.startswith(b"HTTP/") and b" 408 " not in data.split(b"\r\n", 1)[0]


def test_the_drain_still_sees_an_ordinary_timeout():
    """`HeaderDeadline.read` raises `BodyTimeout` for a route and TimeoutError for the drain,
    which sets its own timeout on the socket and treats an OSError as a normal end."""
    class Slow:
        def read1(self, _size):
            raise TimeoutError("planted by the test")

    class Sock:
        def __init__(self, own):
            self.own = own

        def gettimeout(self):
            return self.own
    with pytest.raises(gateway_read_timeout.BodyTimeout):
        gateway_read_timeout.HeaderDeadline(Slow(), LIMIT, Sock(None)).read(10)
    with pytest.raises(TimeoutError) as caught:
        gateway_read_timeout.HeaderDeadline(Slow(), LIMIT, Sock(2.0)).read(10)
    assert isinstance(caught.value, OSError)
    assert not issubclass(gateway_read_timeout.BodyTimeout, Exception)


def test_an_interrupt_is_not_answered_as_a_late_body():
    """`uncaught` answers BodyTimeout and Exception. Anything else is raised again."""
    class Handler:
        path, close_connection = "/api/route", False
    handler = Handler()
    body, status = gateway_read_timeout.uncaught(handler, gateway_read_timeout.BodyTimeout("x"))
    assert status == 408 and handler.close_connection is True
    body, status = gateway_read_timeout.uncaught(Handler(), ValueError("secret text"))
    assert status == 500 and "secret text" not in json.dumps(body)
    with pytest.raises(KeyboardInterrupt):
        gateway_read_timeout.uncaught(Handler(), KeyboardInterrupt())

"""A request the gateway refuses before reading its body leaves no unread bytes.

Windows resets a TCP socket that is closed while received data is still unread,
and the reset can reach the client before it reads the answer. A POST refused
with 401 before its body was read then reached the client as
``ConnectionAbortedError`` (WinError 10053) in about one try in twenty under
memory load, where the gateway meant "authentication required". The same
mechanism sat behind the older inspect-evidence flake.

The deterministic check here is the cause, not the symptom: at the moment the
server shuts the connection down, the socket must hold no unread request bytes.
"""
from __future__ import annotations

import io
import secrets
import socket
import threading
from http.server import ThreadingHTTPServer

import pytest

from harness import gateway
from harness import gateway_body_drain as drain

BODY = b"x" * 48_000            # fits the loopback buffers, so sendall never blocks


class _PeekServer(ThreadingHTTPServer):
    """Records how many request bytes are still unread in the kernel when the
    server shuts a connection down."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.unread: list[int] = []

    def shutdown_request(self, request):
        request.setblocking(False)
        try:
            pending = len(request.recv(1 << 20, socket.MSG_PEEK))
        except BlockingIOError:
            pending = 0
        except OSError:
            pending = -1                  # the client already reset the connection
        request.setblocking(True)
        self.unread.append(pending)
        super().shutdown_request(request)


@pytest.fixture
def server(tmp_path):
    class Handler(gateway._Handler):
        pass

    Handler.flywheel_home = tmp_path / "home"
    Handler.run_root = str(tmp_path / "run")
    Handler.auth_token = secrets.token_urlsafe(32)
    Handler.allowed_hosts = gateway.DEFAULT_HOSTS
    Handler.owner_ref = None
    srv = _PeekServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield srv
    finally:
        srv.shutdown()
        srv.server_close()


def _post(port, path, body):
    return _exchange(port, [f"POST {path} HTTP/1.1", f"Host: 127.0.0.1:{port}",
                            "Content-Type: application/json",
                            f"Content-Length: {len(body)}"], body)


def _exchange(port, head, body):
    """Send one request and read the answer to the end, so the client side
    never closes with unread data of its own."""
    with socket.create_connection(("127.0.0.1", port), timeout=10) as sock:
        sock.sendall(("\r\n".join(head) + "\r\n\r\n").encode("ascii") + body)
        chunks = []
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
    return b"".join(chunks)


def _wait_for(srv, n):
    for _ in range(200):
        if len(srv.unread) >= n:
            return
        threading.Event().wait(0.01)
    raise AssertionError(f"server shut down {len(srv.unread)} of {n} connections")


def test_a_private_post_refused_before_its_body_leaves_nothing_unread(server):
    reply = _post(server.server_port, "/api/plan/run", BODY)
    assert reply.startswith(b"HTTP/1.0 401 ")
    _wait_for(server, 1)
    assert server.unread == [0]


def test_a_public_post_refused_for_its_token_leaves_nothing_unread(server):
    reply = _post(server.server_port, "/api/lanes/gather/call", BODY)
    assert reply.startswith(b"HTTP/1.0 401 ")
    _wait_for(server, 1)
    assert server.unread == [0]


def test_an_unusable_length_is_answered_and_not_drained(server):
    """A length the gateway cannot trust is not read as a body: the gateway
    closes its sending side after the answer, then reads for a bounded time
    and size before it closes."""
    head = ["POST /api/lanes/gather/call HTTP/1.1", f"Host: 127.0.0.1:{server.server_port}",
            "Content-Length: nope"]
    reply = _exchange(server.server_port, head, b"{}")
    assert reply.startswith(b"HTTP/1.0 401 ")
    _wait_for(server, 1)
    assert server.unread == [0]


class _Headers(dict):
    def get(self, key, default=None):
        return super().get(key, default)


def _handler(body, declared, read_first=0):
    handler = type("H", (), {})()
    handler.headers = _Headers({"Content-Length": str(declared)})
    handler.rfile = drain.CountingReader(io.BytesIO(body))
    handler.rfile.start_body()
    if read_first:
        handler.rfile.read(read_first)
    handler.connection = None
    return handler


def test_the_drain_reads_exactly_what_the_handler_left():
    handler = _handler(b"a" * 100 + b"NEXT", 100, read_first=30)
    assert drain.drain_unread_body(handler) == ("drained", 70)
    assert handler.rfile.read() == b"NEXT"


def test_a_body_the_handler_read_whole_is_left_alone():
    handler = _handler(b"a" * 100, 100, read_first=100)
    assert drain.drain_unread_body(handler) == ("complete", 0)


def test_a_body_over_the_bound_is_not_read_in_full(monkeypatch):
    monkeypatch.setattr(drain, "DRAIN_LIMIT", 10)
    handler = _handler(b"a" * 100, 100)
    status, read = drain.drain_unread_body(handler)
    assert status == "lingered" and read <= 10


def test_a_handler_without_the_counting_reader_is_left_alone():
    handler = type("H", (), {"rfile": io.BytesIO(b"abc"), "headers": _Headers()})()
    assert drain.drain_unread_body(handler) == ("not_counted", 0)

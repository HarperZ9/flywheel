"""A loopback upstream is connected without the Windows timer wait.

Fifth review round of 2.0.0. The gateway overhead gate failed on Windows
runners with a tail before the first byte. One cause was the connect: a Python
socket that has a timeout connects without blocking and then waits, and on
Windows that wait is a timer tick late for a quarter to a half of loopback
connects (harness/endpoints_connect.py has the measurement). The gateway's
upstream transport now connects to a loopback address blocking and sets the
timeout afterwards.

These tests check the rule, not the clock: which connects are made blocking,
that the timeout is on the socket afterwards, and that every other connect is
left to `socket.create_connection`. The timing itself is measured, and its
budget enforced, by tests/test_gateway_overhead_timing.py.
"""
import socket
import threading

import pytest

from harness import endpoints_connect, endpoints_http

pytestmark = pytest.mark.release_gate   # run against the built wheel before a release


@pytest.fixture
def listener():
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(8)
    accepted = []

    def accept():
        while True:
            try:
                conn, _ = server.accept()
            except OSError:
                return
            accepted.append(conn)
    threading.Thread(target=accept, daemon=True).start()
    yield server.getsockname()[1]
    server.close()
    for conn in accepted:
        conn.close()


class _Recording(socket.socket):
    """A socket that notes the timeout it had when `connect` was called."""
    at_connect = []

    def connect(self, address):
        _Recording.at_connect.append(self.gettimeout())
        return super().connect(address)


@pytest.fixture
def recorded(monkeypatch):
    _Recording.at_connect = []
    monkeypatch.setattr(endpoints_connect.socket, "socket", _Recording)
    return _Recording.at_connect


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost"])
def test_on_windows_a_loopback_connect_is_blocking_and_the_timeout_is_set_after(
        monkeypatch, listener, recorded, host):
    monkeypatch.setattr(endpoints_connect, "WINDOWS", True)
    sock = endpoints_connect.create_connection((host, listener), 600.0)
    try:
        assert recorded[-1] is None, "the connect was made with a timeout on the socket"
        assert sock.gettimeout() == 600.0           # reads and writes are still bounded
    finally:
        sock.close()


@pytest.mark.parametrize("windows, host, timeout", [
    (False, "127.0.0.1", 600.0),        # another system: as before
    (True, "127.0.0.1", None),          # no timeout asked for: as before
])
def test_control_every_other_connect_is_left_as_it_was(
        monkeypatch, listener, recorded, windows, host, timeout):
    monkeypatch.setattr(endpoints_connect, "WINDOWS", windows)
    sock = endpoints_connect.create_connection((host, listener), timeout)
    try:
        assert recorded[-1] == timeout              # connected the way the caller asked
    finally:
        sock.close()


def test_a_host_that_is_not_loopback_is_not_connected_blocking(monkeypatch):
    monkeypatch.setattr(endpoints_connect, "WINDOWS", True)
    asked = []

    def create(address, timeout, source_address):
        asked.append((address, timeout))
        raise OSError("planted: no network in this test")
    monkeypatch.setattr(endpoints_connect.socket, "create_connection", create)
    with pytest.raises(OSError, match="planted"):
        endpoints_connect.create_connection(("api.example.invalid", 443), 30.0)
    assert asked == [(("api.example.invalid", 443), 30.0)]


@pytest.mark.parametrize("host, expected", [
    ("127.0.0.1", True), ("127.8.9.10", True), ("::1", True), ("[::1]", True),
    ("localhost", True), ("LOCALHOST", True), ("10.0.0.5", False), ("api.openai.com", False),
    ("localhost.example.com", False), ("", False),
])
def test_what_counts_as_loopback(host, expected):
    assert endpoints_connect.loopback(host) is expected


def test_a_refused_loopback_connect_is_still_an_error(monkeypatch):
    monkeypatch.setattr(endpoints_connect, "WINDOWS", True)
    spare = socket.socket()
    spare.bind(("127.0.0.1", 0))
    port = spare.getsockname()[1]
    spare.close()                                   # nothing listens there now
    with pytest.raises(OSError):
        endpoints_connect.create_connection(("127.0.0.1", port), 5.0)


def test_the_gateway_transport_uses_it():
    """The opener every upstream request goes through has the prompt-connect handler."""
    kinds = [type(handler) for handler in endpoints_http._OPENER.handlers]
    assert endpoints_connect.Handler in kinds

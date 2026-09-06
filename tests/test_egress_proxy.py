"""The one route out of a confined run: what it carries, and what it stops.

Two halves are exercised separately on purpose. The decision is asserted
without opening a socket, so a name that answers with a loopback address is
proved refused rather than assumed. The relay is asserted against a server
this file starts, with resolution injected, so bytes are proved to arrive
without asking the network anything.

No test here reaches DNS or the internet. A suite that did would be a suite
that fails on an offline machine for a reason it is not about.
"""
import socket
import threading

import pytest

from harness.egress_policy import EgressPolicy
from harness.egress_proxy import (MAX_HEAD, Attempt, EgressProxy, ProxyRefused,
                                  parse_connect, serve)

#: An address outside every range `blocked_address` refuses, so the guard
#: runs for real in the relay tests and passes.
PUBLIC = "93.184.216.34"

HEAD = b"CONNECT pypi.org:443 HTTP/1.1\r\nHost: pypi.org:443\r\n\r\n"


def _listener():
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(8)
    return sock


def _read_until(conn, marker, limit=8192):
    buffer = b""
    while marker not in buffer and len(buffer) < limit:
        chunk = conn.recv(limit)
        if not chunk:
            break
        buffer += chunk
    return buffer


class _Origin:
    """A server the proxy is allowed to reach. It echoes what it is sent."""

    def __init__(self):
        self.sock = _listener()
        self.port = self.sock.getsockname()[1]
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        self.sock.settimeout(0.5)
        while not self.stop.is_set():
            try:
                conn, _ = self.sock.accept()
            except (socket.timeout, TimeoutError):
                continue
            except OSError:
                return
            threading.Thread(target=self._echo, args=(conn,),
                             daemon=True).start()

    def _echo(self, conn):
        with conn:
            while True:
                try:
                    data = conn.recv(4096)
                except OSError:
                    return
                if not data:
                    return
                conn.sendall(data)

    def close(self):
        self.stop.set()
        self.thread.join(timeout=3)
        self.sock.close()


@pytest.fixture
def origin():
    server = _Origin()
    yield server
    server.close()


@pytest.fixture
def proxied(origin):
    """A running proxy in front of a server this test controls.

    `resolve` answers with a public address, so the address guard runs and
    passes rather than being skipped. `connect_to` ignores that address and
    dials the local origin, so the bytes land somewhere the test can read.
    """
    proxy = EgressProxy(
        EgressPolicy(hosts=("pypi.org", "*.pythonhosted.org")),
        resolve=lambda host, port: [PUBLIC],
        connect_to=lambda address, port: socket.create_connection(
            ("127.0.0.1", origin.port), timeout=5))
    listener = _listener()
    stop = threading.Event()
    thread = threading.Thread(target=serve, args=(proxy, listener, stop),
                              daemon=True)
    thread.start()
    yield proxy, listener.getsockname()[1]
    stop.set()
    thread.join(timeout=5)
    listener.close()


def _client(port):
    conn = socket.create_connection(("127.0.0.1", port), timeout=5)
    conn.settimeout(5)
    return conn


def test_a_connect_line_gives_up_its_host_and_port():
    assert parse_connect(HEAD) == ("pypi.org", 443)
    assert parse_connect(b"connect a.test:8443 HTTP/1.1\r\n\r\n") == (
        "a.test", 8443)


def test_a_bracketed_address_is_unwrapped_to_the_form_a_policy_holds():
    """A target spells an IPv6 literal in brackets and a policy does not."""
    assert parse_connect(b"CONNECT [2606:4700::1]:443 HTTP/1.1\r\n\r\n") == (
        "2606:4700::1", 443)


@pytest.mark.parametrize("line", [
    b"GET http://pypi.org/simple HTTP/1.1\r\n\r\n",
    b"CONNECT pypi.org HTTP/1.1\r\n\r\n",
    b"CONNECT pypi.org:https HTTP/1.1\r\n\r\n",
    b"CONNECT :443 HTTP/1.1\r\n\r\n",
    b"CONNECT pypi.org:443\r\n\r\n",
    b"\r\n\r\n",
])
def test_anything_that_is_not_a_readable_connect_is_refused(line):
    with pytest.raises(ProxyRefused):
        parse_connect(line)


def test_a_host_outside_the_policy_never_reaches_a_socket():
    """The denial has to happen before the dial, not after it.

    A proxy that connected and then closed would still have told the
    upstream host that this machine wanted it.
    """
    dialled = []
    proxy = EgressProxy(EgressPolicy(hosts=("pypi.org",)),
                        resolve=lambda host, port: [PUBLIC],
                        connect_to=lambda a, p: dialled.append(a))
    with pytest.raises(ProxyRefused, match="not-allowed"):
        proxy.upstream("telemetry.test", 443)
    assert dialled == []
    assert proxy.attempts == [Attempt("telemetry.test", 443, False,
                                      "not-allowed")]


def test_an_allowed_name_that_answers_with_loopback_is_refused():
    """The case the address guard exists for.

    Nothing in the policy names the loopback interface. A DNS answer can,
    and a policy that stopped at the name would carry the request there.
    """
    dialled = []
    proxy = EgressProxy(EgressPolicy(hosts=("pypi.org",)),
                        resolve=lambda host, port: ["127.0.0.1"],
                        connect_to=lambda a, p: dialled.append(a))
    with pytest.raises(ProxyRefused, match="loopback"):
        proxy.upstream("pypi.org", 443)
    assert dialled == []
    assert proxy.attempts[0].reason == "loopback"
    assert proxy.attempts[0].address == "127.0.0.1", (
        "the receipt has to name the address that was refused, or a reader "
        "cannot tell which answer did it")


def test_one_bad_address_refuses_the_whole_answer():
    """A name answering with a public address and a loopback one is being
    used to reach the loopback one. Picking the allowed sibling would serve
    the request and lose the signal."""
    proxy = EgressProxy(EgressPolicy(hosts=("pypi.org",)),
                        resolve=lambda host, port: [PUBLIC, "169.254.169.254"],
                        connect_to=lambda a, p: pytest.fail("dialled anyway"))
    with pytest.raises(ProxyRefused, match="link-local"):
        proxy.upstream("pypi.org", 443)


def test_a_resolver_that_answers_with_nothing_is_a_refusal():
    proxy = EgressProxy(EgressPolicy(hosts=("pypi.org",)),
                        resolve=lambda host, port: [])
    with pytest.raises(ProxyRefused, match="resolve-empty"):
        proxy.upstream("pypi.org", 443)
    assert proxy.attempts[0].allowed is False


def test_a_resolver_that_fails_is_a_refusal_and_not_a_crash():
    def angry(host, port):
        raise socket.gaierror("no answer")

    proxy = EgressProxy(EgressPolicy(hosts=("pypi.org",)), resolve=angry)
    with pytest.raises(ProxyRefused, match="resolve-failed"):
        proxy.upstream("pypi.org", 443)


def test_an_allowed_host_gets_a_tunnel_that_carries_bytes(proxied):
    """End to end: policy, address guard, tunnel, and the log entry."""
    proxy, port = proxied
    conn = _client(port)
    conn.sendall(HEAD)
    assert _read_until(conn, b"\r\n\r\n").startswith(b"HTTP/1.1 200")
    conn.sendall(b"ping")
    assert _read_until(conn, b"ping") == b"ping"
    conn.close()
    assert proxy.attempts == [Attempt("pypi.org", 443, True, "allowed", PUBLIC)]


def test_bytes_sent_before_the_reply_are_not_dropped(proxied):
    """A client that does not wait for the 200 would otherwise lose its
    first record, which for a TLS client is the handshake."""
    proxy, port = proxied
    conn = _client(port)
    conn.sendall(HEAD + b"early")
    answer = _read_until(conn, b"early")
    assert answer.startswith(b"HTTP/1.1 200")
    assert answer.endswith(b"early")
    conn.close()


def test_a_refused_client_is_told_the_reason_in_our_own_words(proxied):
    """The reason is a code from this module. Nothing the client wrote is
    copied into the reply, so nothing it wrote can reach a header line."""
    proxy, port = proxied
    conn = _client(port)
    conn.sendall(b"CONNECT evil.test:443 HTTP/1.1\r\nHost: evil.test\r\n\r\n")
    answer = _read_until(conn, b"not-allowed")
    conn.close()
    assert answer.startswith(b"HTTP/1.1 403")
    assert b"not-allowed" in answer
    assert b"evil.test" not in answer


def test_a_head_that_never_ends_is_refused_rather_than_read(proxied):
    proxy, port = proxied
    conn = _client(port)
    conn.sendall(b"CONNECT pypi.org:443 HTTP/1.1\r\nX: " + b"a" * MAX_HEAD)
    assert b"head-too-large" in _read_until(conn, b"head-too-large")
    conn.close()


def test_the_record_carries_the_refusals_as_well_as_the_connections(proxied):
    """Where a run went, not only where it could have gone.

    A receipt holding the policy alone tells a reader what was permitted. A
    denied request is the entry that changes a reader's mind, so it is the
    one that must survive into the record.
    """
    proxy, port = proxied
    for target in (b"pypi.org:443", b"telemetry.test:443"):
        conn = _client(port)
        conn.sendall(b"CONNECT " + target + b" HTTP/1.1\r\n\r\n")
        _read_until(conn, b"\r\n\r\n")
        conn.close()
    record = proxy.record()
    assert record["schema"].startswith("flywheel.egress-attempts/")
    assert record["policy"]["hosts"] == ["pypi.org", "*.pythonhosted.org"]
    seen = {(one["host"], one["allowed"], one["reason"])
            for one in record["attempts"]}
    assert ("pypi.org", True, "allowed") in seen
    assert ("telemetry.test", False, "not-allowed") in seen

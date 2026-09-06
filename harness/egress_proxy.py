"""egress_proxy.py -- the one route out of a confined run, and its log.

A confined run gets no network namespace of its own to route with. What it
gets is one endpoint, and this is what sits on the other side of it. Every
connection the run wants arrives here first as a CONNECT line naming a host
and a port, and leaves here only if `egress_policy` names them too.

The log is the reason this is worth building rather than borrowing. A
policy states what a run was permitted to reach. `Attempt` states what it
actually asked for, including the requests that were refused, so a receipt
carries where a run went and not only where it could have gone.

Only CONNECT is served. A plain proxied `GET http://host/path` would put
this in the middle of a cleartext request, reading and forwarding a body it
has no business touching, and the extra parsing would be several more ways
to be wrong about what was sent. A client that wants that is refused and
told which method is served.

Resolution happens here and not in the confined process, which has no route
to a resolver. That is worth naming: the host in the CONNECT line is the
host the client meant, unshortened by anything the client's own resolver
did first.
"""
from __future__ import annotations

import selectors
import socket
import threading
from dataclasses import dataclass

from .egress_policy import EgressPolicy, blocked_address

SCHEMA = "flywheel.egress-attempts/v1"

#: The most request head this will read before giving up. A CONNECT line
#: and its headers are small, and a client that sends more than this is
#: either not speaking the protocol or trying to make the reader the
#: interesting part of the program.
MAX_HEAD = 8192

#: How long a single upstream connect may take. A refusal is a result. A
#: hang is a run that never ends.
DIAL_TIMEOUT = 20.0

#: How often an open tunnel wakes to check whether either side has gone.
#: An idle tunnel is a normal tunnel, so this is a poll interval and not a
#: deadline: nothing here closes a connection for being quiet.
SPLICE_POLL = 30.0

ESTABLISHED = b"HTTP/1.1 200 Connection established\r\n\r\n"


def _refusal(reason: str) -> bytes:
    """The reply a denied client gets. The reason is a fixed code from this
    module, never text the client sent, so nothing it wrote can reach a
    header line."""
    body = f"egress denied: {reason}".encode()
    return (b"HTTP/1.1 403 Forbidden\r\n"
            b"Content-Type: text/plain\r\n"
            b"Content-Length: " + str(len(body)).encode() + b"\r\n"
            b"Connection: close\r\n\r\n" + body)


class ProxyRefused(ValueError):
    """The request cannot be served. The message is the reason code."""


@dataclass(frozen=True)
class Attempt:
    """One request, allowed or not, as it will read in a receipt."""

    host: str
    port: int
    allowed: bool
    reason: str
    address: str = ""

    def record(self) -> dict:
        return {"host": self.host, "port": self.port,
                "allowed": self.allowed, "reason": self.reason,
                "address": self.address}


def parse_connect(head: bytes) -> tuple:
    """The host and port of a CONNECT request line, or a refusal.

    The line is `CONNECT host:port HTTP/1.1`. A bracketed IPv6 literal is
    unwrapped, since that is how the address is spelled in a target and not
    how it is spelled in a policy.
    """
    line = head.split(b"\r\n", 1)[0].decode("latin-1").strip()
    parts = line.split()
    if len(parts) != 3 or parts[0].upper() != "CONNECT":
        raise ProxyRefused("not-connect")
    target = parts[1]
    if target.startswith("["):
        host, _, rest = target[1:].partition("]")
        port_text = rest.lstrip(":")
    else:
        host, _, port_text = target.rpartition(":")
    if not host or not port_text.isdigit():
        raise ProxyRefused("bad-target")
    return host, int(port_text)


def read_head(conn) -> bytes:
    """Everything up to the blank line ending the request head."""
    buffer = b""
    while b"\r\n\r\n" not in buffer:
        if len(buffer) >= MAX_HEAD:
            raise ProxyRefused("head-too-large")
        chunk = conn.recv(1024)
        if not chunk:
            raise ProxyRefused("closed-early")
        buffer += chunk
    return buffer


class EgressProxy:
    """Serves CONNECT for one confined run, and remembers every request.

    `resolve` and `connect_to` are injectable so the decision and the relay
    can each be exercised without the other: a test can prove a name that
    answers with a loopback address is refused without opening a socket, and
    prove the relay carries bytes without asking a real resolver anything.
    """

    def __init__(self, policy: EgressPolicy, *, resolve=None, connect_to=None):
        self.policy = policy
        self.attempts: list = []
        self._lock = threading.Lock()
        self._resolve = resolve if resolve is not None else _resolve
        self._connect = connect_to if connect_to is not None else _connect

    def record(self) -> dict:
        with self._lock:
            attempts = [one.record() for one in self.attempts]
        return {"schema": SCHEMA, "policy": self.policy.record(),
                "attempts": attempts}

    def _note(self, attempt: Attempt) -> Attempt:
        with self._lock:
            self.attempts.append(attempt)
        return attempt

    def upstream(self, host: str, port: int):
        """A socket to `host`, or a refusal naming why there is none.

        Every address the name answers with is checked, and one bad address
        refuses the whole request rather than sending it to an allowed
        sibling. A name that answers with a public address and a loopback
        one is being used to reach the loopback one.
        """
        if not self.policy.allows(host, port):
            self._note(Attempt(host, port, False, "not-allowed"))
            raise ProxyRefused("not-allowed")
        try:
            addresses = list(self._resolve(host, port))
        except OSError:
            self._note(Attempt(host, port, False, "resolve-failed"))
            raise ProxyRefused("resolve-failed")
        if not addresses:
            self._note(Attempt(host, port, False, "resolve-empty"))
            raise ProxyRefused("resolve-empty")
        for address in addresses:
            bad = blocked_address(address)
            if bad is not None:
                self._note(Attempt(host, port, False, bad, address))
                raise ProxyRefused(bad)
        try:
            sock = self._connect(addresses[0], port)
        except OSError:
            self._note(Attempt(host, port, False, "connect-failed",
                               addresses[0]))
            raise ProxyRefused("connect-failed")
        self._note(Attempt(host, port, True, "allowed", addresses[0]))
        return sock

    def handle(self, conn) -> None:
        """One client connection, start to finish. Never raises.

        Whatever arrived after the blank line is forwarded before the relay
        starts. A client is meant to wait for the 200 before it sends, and
        one that does not would otherwise lose its first record here, which
        for a TLS client is the handshake and reads as a hang rather than as
        a bug in this function.
        """
        upstream = None
        try:
            head = read_head(conn)
            host, port = parse_connect(head)
            upstream = self.upstream(host, port)
            conn.sendall(ESTABLISHED)
            early = head.split(b"\r\n\r\n", 1)[1]
            if early:
                upstream.sendall(early)
            splice(conn, upstream)
        except ProxyRefused as refused:
            _quiet(conn.sendall, _refusal(str(refused)))
        except OSError:
            pass
        finally:
            for sock in (conn, upstream):
                if sock is not None:
                    _quiet(sock.close)


def splice(left, right) -> None:
    """Carry bytes both ways until one side is done.

    Nothing here reads what passes. The policy decided the destination and
    the tunnel is a tunnel. A proxy that inspected the stream would be a
    second thing to be wrong about, on the traffic this exists to permit.
    """
    selector = selectors.DefaultSelector()
    selector.register(left, selectors.EVENT_READ, right)
    selector.register(right, selectors.EVENT_READ, left)
    try:
        while True:
            for key, _ in selector.select(timeout=SPLICE_POLL):
                data = key.fileobj.recv(65536)
                if not data:
                    return
                key.data.sendall(data)
    except OSError:
        return
    finally:
        selector.close()


def serve(proxy: EgressProxy, listener, stop: threading.Event) -> None:
    """Accept until `stop` is set. One thread per connection.

    The listener carries the timeout, so a run whose command exits without
    closing a connection still lets this loop notice `stop` and return.
    """
    listener.settimeout(0.5)
    workers: list = []
    while not stop.is_set():
        try:
            conn, _ = listener.accept()
        except (socket.timeout, TimeoutError):
            continue
        except OSError:
            break
        worker = threading.Thread(target=proxy.handle, args=(conn,),
                                  daemon=True)
        worker.start()
        workers.append(worker)
    for worker in workers:
        worker.join(timeout=1.0)


def _resolve(host: str, port: int) -> list:
    """Every address this name answers with, as text."""
    found = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    seen, out = set(), []
    for entry in found:
        address = entry[4][0]
        if address not in seen:
            seen.add(address)
            out.append(address)
    return out


def _connect(address: str, port: int):
    return socket.create_connection((address, port), timeout=DIAL_TIMEOUT)


def _quiet(call, *args) -> None:
    try:
        call(*args)
    except OSError:
        pass

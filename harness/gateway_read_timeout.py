"""gateway_read_timeout.py -- a client may not hold a gateway connection silent.

Without a receive timeout a client can send request headers and then nothing,
for any length of time. Each such connection holds a gateway thread, and a
request that is admitted long after its headers arrived was once checked
against key totals that were out of date (the key row is now read again after
the body; see gateway_key_gate.enter).

`arm` sets a receive timeout on the socket of each connection the gateway
accepts. Every read of the request line, the headers and the body must get
some bytes within that many seconds, or the connection is closed:

  - a silent request line or header: `http.server` closes the connection;
  - a silent body on a model interface: the gateway answers 408 and closes
    (gateway_interfaces.serve), and nothing is sent upstream.

The default is 30 seconds. FLYWHEEL_GATEWAY_READ_TIMEOUT sets another number
of seconds; `0` or `off` removes the timeout and the two deadlines below.

The timeout is per read, so a client that keeps sending a few bytes would
never meet it. Two deadlines bound that, and both apply before the gateway
knows who is calling:

  - the request line and headers of one request must arrive within one
    timeout (`HeaderDeadline.readline`, on every route);
  - a request body must arrive within BODY_READS timeouts, two minutes by
    default. The answer is 408 on every route: on a model interface from
    `read_body`, and on the other routes, which read their bodies in
    gateway.py and the route modules, from `HeaderDeadline.read`, which
    raises `BodyTimeout` (answered by `uncaught`);
  - what a refused request still sends is read and discarded for at most two
    seconds (gateway_body_drain, bounded by `HeaderDeadline.read`).

A slow client costs a thread and no provider spend, because nothing is
admitted before the body is whole. Writes have no timeout, and there is no
cap on the number of open connections.

The timeout is the operating system's own (SO_RCVTIMEO), set on a socket that
stays in blocking mode, so the way the gateway reads and writes is what it
was before the timeout existed. Python's `socket.settimeout` was the first
form and was replaced: it changes the socket's mode for reads and writes
alike. With it, one Windows CI run measured 55 to 230 ms of gateway overhead
a call (run 43633574345) and a second run of the same commit measured 16 to
24 ms (run 43633577283), where main measures 7 to 22 ms. Whether the timeout
caused the slow run was not established. What a timed-out read looks like
differs by system, and `read_body` hides the difference: Windows raises
TimeoutError; Linux and macOS return the bytes that had arrived.
"""
from __future__ import annotations

import logging
import os
import socket
import struct
import time
import uuid

_LOG = logging.getLogger(__name__)
ENV = "FLYWHEEL_GATEWAY_READ_TIMEOUT"


class BodyTimeout(BaseException):
    """A request body that stopped arriving, or was still arriving at its deadline,
    on a route outside the three model interfaces.

    It is not an `Exception` on purpose. Twenty places read a request body
    with `handler.rfile.read(n)`, and several wrap the read in `except
    Exception` and answer their own error: the operation grant step answered
    500 `STORE_COMMIT_FAILED` for it, others read the late body as an empty
    one. None of them can catch this, so it reaches the gateway handler, which
    answers 408 and closes (`uncaught`). Nothing has been sent upstream at
    that point: every route reads its body first."""
DEFAULT = 30.0
BODY_READS = 4                          # a whole body gets this many read timeouts
_CHUNK = 1 << 20


def seconds(environ=None) -> "float | None":
    """The timeout in seconds, or None when it is switched off."""
    raw = ((os.environ if environ is None else environ).get(ENV) or "").strip().lower()
    if raw in ("0", "off", "none", "no", "false"):
        return None
    try:
        value = float(raw) if raw else DEFAULT
    except ValueError:
        _LOG.warning("%s is not a number of seconds; the default of %s is used", ENV, DEFAULT)
        return DEFAULT
    return value if value > 0 else None


def arm(handler) -> None:
    """Set the receive timeout on a handler's connection. Called from the gateway
    handler's `setup` (gateway_body_drain.BodyDrainMixin), once per connection."""
    limit = seconds()
    sock = getattr(handler, "connection", None)
    if limit is None or sock is None:
        return
    whole = int(limit)
    value = (max(1, int(limit * 1000)) if os.name == "nt"       # DWORD milliseconds
             else struct.pack("ll", whole, int((limit - whole) * 1_000_000)))   # timeval
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVTIMEO, value)
    except (OSError, AttributeError) as exc:
        _LOG.warning("gateway connection has no read timeout: SO_RCVTIMEO could not be set "
                     "(%s: %s)", type(exc).__name__, exc)
    if hasattr(getattr(handler, "rfile", None), "peek"):
        handler.rfile = HeaderDeadline(handler.rfile, limit, sock)


class HeaderDeadline:
    """The connection's reader, with a deadline for each request head and each body read.

    `http.server` reads the request line and the headers with `readline`. The
    clock starts at the first of those reads and stops at the blank line that
    ends the headers. A line asked for after the deadline raises TimeoutError,
    which `http.server` answers by closing the connection. A client that sends
    a header line every few seconds, with or without a credential, is closed
    after `limit` seconds and at most one more read.

    `read(n)` is how every other reader of a body asks for it: the routes in
    gateway.py, and the drain that discards what a refused request still sends
    (gateway_body_drain). A plain buffered `read(n)` waits until all `n` bytes
    are there, so a client that sent one byte at a time held the thread for as
    long as it liked, also after a 401. Here one `read(n)` gets a budget: the
    socket's own timeout while one is set (the drain sets two seconds), else
    BODY_READS read timeouts. Past it, TimeoutError."""

    def __init__(self, raw, limit: float, sock=None):
        self._raw, self._limit, self._until, self._sock = raw, limit, None, sock

    def __getattr__(self, name: str):
        return getattr(self._raw, name)

    def _budget(self) -> tuple:
        """(seconds one `read(n)` may take, is the reader the drain)."""
        try:
            own = self._sock.gettimeout() if self._sock is not None else None
        except OSError:
            own = None
        return own or self._limit * BODY_READS, bool(own)

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            return self._raw.read()
        budget, draining = self._budget()
        # The drain sets its own two-second timeout on the socket and expects an OSError.
        # Every other reader is a route reading its request body: `BodyTimeout`.
        late = TimeoutError if draining else BodyTimeout
        started, parts, got = time.monotonic(), [], 0
        while got < size:
            try:
                chunk = self._raw.read1(min(size - got, _CHUNK))
            except TimeoutError as exc:         # Windows: a read that got nothing in time
                raise late(f"a request body stopped at {got} of {size} bytes") from exc
            if not chunk:
                break                           # closed, or a read that timed out with nothing
            parts.append(chunk)
            got += len(chunk)
            if got < size and time.monotonic() - started > budget:
                raise late(f"a request body was still arriving after {budget} seconds, "
                           f"at {got} of {size} bytes")
        if got < size and late is BodyTimeout and (
                time.monotonic() - started >= self._limit * 0.9):
            raise late(f"a request body stopped at {got} of {size} bytes")   # Linux, macOS
        return b"".join(parts)

    def readline(self, size: int = -1) -> bytes:
        if self._until is None:
            self._until = time.monotonic() + self._limit
        line = b""
        while size < 0 or len(line) < size:
            if time.monotonic() > self._until:
                raise TimeoutError(f"the request head did not arrive within {self._limit} s")
            seen = self._raw.peek(1)            # one read of the socket at most
            if not seen:
                break                           # closed, or a read that timed out with nothing
            cut = seen.find(b"\n") + 1
            take = cut or len(seen)
            line += self._raw.read(take if size < 0 else min(take, size - len(line)))
            if line.endswith(b"\n"):
                break
        if line in (b"\r\n", b"\n", b""):
            self._until = None                  # the head is over; the next one starts a clock
        return line


def read_body(handler, length: int) -> bytes:
    """The request body. Raises TimeoutError when it stopped arriving, or when the
    whole of it did not arrive within BODY_READS read timeouts.

    A body the client cut short by closing its side comes back short, as
    before, and the caller answers it as a body that is not JSON."""
    limit, started = seconds(), time.monotonic()
    if limit is None:
        return handler.rfile.read(length) or b""
    parts, got = [], 0
    while got < length:
        chunk = handler.rfile.read1(min(length - got, _CHUNK))   # Windows raises TimeoutError
        if not chunk:
            break                               # closed, or a read that timed out with nothing
        parts.append(chunk)
        got += len(chunk)
        if got < length and time.monotonic() - started > limit * BODY_READS:
            raise TimeoutError(f"the request body was still arriving after {limit * BODY_READS} "
                               f"seconds, at {got} of {length} bytes")
    if got < length and time.monotonic() - started >= limit * 0.9:
        raise TimeoutError(f"the request body stopped at {got} of {length} bytes")
    return b"".join(parts)


def uncaught(handler, exc: BaseException) -> tuple:
    """(body, status) for what reached the gateway handler uncaught.

    A late body (`BodyTimeout`) is answered 408 and the connection is closed.
    Any other `Exception` is the handler's non-echoing 500, as before.
    Anything else (an interrupt, an exit) is raised again."""
    if isinstance(exc, BodyTimeout):
        limit = seconds()
        _LOG.warning("gateway request on %s closed: its body did not arrive within the read "
                     "timeout (%s s)", str(getattr(handler, "path", "")).split("?", 1)[0], limit)
        handler.close_connection = True
        return {"error": {
            "message": (f"the request body did not arrive within the gateway's read timeout "
                        f"of {limit} seconds ({ENV}). Nothing was sent upstream."),
            "type": "invalid_request_error", "code": "request_timeout"}}, 408
    if not isinstance(exc, Exception):
        raise exc
    return {"error": {"message": f"internal error: {type(exc).__name__}",
                      "type": "api_error"}}, 500


def timed_out(handler, path: str):
    """The 408 `Response` for a request body that stopped arriving."""
    from .gateway_turn import Response
    limit = seconds()
    _LOG.warning("gateway request on %s closed: its body did not arrive within the read "
                 "timeout (%s s)", path, limit)
    handler.close_connection = True
    text = (f"the request body did not arrive within the gateway's read timeout of {limit} "
            f"seconds ({ENV}). Nothing was sent upstream.")
    request_id = f"req_fw_{uuid.uuid4().hex[:24]}"
    if path == "/v1/responses":
        from .gateway_responses_reply import error
        return Response(408, error(408, text, None, "request_timeout"),
                        headers={"x-request-id": request_id, "Connection": "close"})
    from .gateway_messages_wire import error
    return Response(408, error(408, text, request_id),
                    headers={"request-id": request_id, "Connection": "close"})

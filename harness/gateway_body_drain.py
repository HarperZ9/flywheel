"""Read what a request sent before the gateway closes its connection.

The gateway answers several refusals without reading the request body: 401
before authentication, 400 on an unusable length, and the size and media-type
refusals of some routes. Windows resets a TCP socket that is closed while
received data is still unread, and that reset can reach the client before it
reads the answer. The client then sees a connection abort (WinError 10053 or
10054) where the gateway meant a refusal.

``BodyDrainMixin`` counts the body bytes a handler reads. When the handler is
done and before the server shuts the connection down, ``drain_unread_body``
reads and discards what the handler left:

- a declared length up to ``DRAIN_LIMIT`` is read in full, within
  ``DRAIN_SECONDS``;
- a larger or unusable length is not read in full. The gateway closes its
  sending side first, so the answer is complete on the wire, and then reads
  for a bounded time and size before it closes (a lingering close).

Nothing here changes an answer. A connection the client drops during the drain
is a normal end, reported as ``aborted`` to the caller.
"""
from __future__ import annotations

import socket
import time
from typing import Any

DRAIN_LIMIT = 4 * 1024 * 1024
DRAIN_SECONDS = 2.0
_CHUNK = 64 * 1024


class CountingReader:
    """A read-only stand-in for the handler's ``rfile`` that counts the body
    bytes read after ``start_body``."""

    def __init__(self, raw: Any):
        self._raw = raw
        self._mark: int | None = None
        self._total = 0

    def __getattr__(self, name: str) -> Any:
        return getattr(self._raw, name)

    def _count(self, data: bytes) -> bytes:
        self._total += len(data)
        return data

    def read(self, *args: Any) -> bytes:
        return self._count(self._raw.read(*args))

    def read1(self, *args: Any) -> bytes:
        return self._count(self._raw.read1(*args))

    def readline(self, *args: Any) -> bytes:
        return self._count(self._raw.readline(*args))

    def readinto(self, buffer: Any) -> int:
        n = self._raw.readinto(buffer)
        self._total += n or 0
        return n

    def start_body(self) -> None:
        """The request line and headers are read; count from here."""
        self._mark = self._total

    def clear_body(self) -> None:
        """A new request starts; nothing is known about its body yet."""
        self._mark = None

    @property
    def body_read(self) -> int | None:
        return None if self._mark is None else self._total - self._mark


def _declared_length(handler: Any) -> int | None:
    try:
        length = int(handler.headers.get("Content-Length", 0))
    except (AttributeError, TypeError, ValueError):
        return None
    return length if length >= 0 else None


def _discard(rfile: CountingReader, limit: int, deadline: float) -> tuple[int, bool]:
    """Read up to ``limit`` bytes before ``deadline``; (bytes read, hit EOF)."""
    read = 0
    while read < limit and time.monotonic() < deadline:
        chunk = rfile.read(min(_CHUNK, limit - read))
        if not chunk:
            return read, True
        read += len(chunk)
    return read, False


def drain_unread_body(handler: Any) -> tuple[str, int]:
    """Read and discard the body bytes ``handler`` left unread.

    Returns (status, bytes discarded). Status is one of ``not_counted`` (the
    handler's reader does not count, as in unit tests), ``complete`` (nothing
    left), ``drained``, ``lingered`` (length too large or unusable) or
    ``aborted`` (the client closed or reset the connection first)."""
    rfile = getattr(handler, "rfile", None)
    if not isinstance(rfile, CountingReader) or rfile.body_read is None:
        return "not_counted", 0
    declared = _declared_length(handler)
    left = None if declared is None else declared - rfile.body_read
    if left is not None and left <= 0:
        return "complete", 0
    sock = getattr(handler, "connection", None)
    deadline = time.monotonic() + DRAIN_SECONDS
    before = sock.gettimeout() if sock is not None else None
    try:
        if sock is not None:
            sock.settimeout(DRAIN_SECONDS)
        if left is not None and left <= DRAIN_LIMIT:
            read, _eof = _discard(rfile, left, deadline)
            return "drained", read
        handler.close_connection = True
        if sock is not None:
            handler.wfile.flush()
            sock.shutdown(socket.SHUT_WR)
        read, _eof = _discard(rfile, DRAIN_LIMIT, deadline)
        return "lingered", read
    except OSError:
        handler.close_connection = True
        return "aborted", 0
    finally:
        if sock is not None:
            try:
                sock.settimeout(before)
            except OSError:
                pass                      # the socket is already closed


class BodyDrainMixin:
    """Mix in before ``BaseHTTPRequestHandler``: count body reads, and after
    each request drain what the handler left, before the server shuts the
    connection down."""

    def setup(self) -> None:
        super().setup()  # type: ignore[misc]
        self.rfile = CountingReader(self.rfile)

    def parse_request(self) -> bool:
        ok = super().parse_request()  # type: ignore[misc]
        if ok and isinstance(self.rfile, CountingReader):
            self.rfile.start_body()
        return ok

    def handle_one_request(self) -> None:
        if isinstance(self.rfile, CountingReader):
            self.rfile.clear_body()
        super().handle_one_request()  # type: ignore[misc]
        drain_unread_body(self)

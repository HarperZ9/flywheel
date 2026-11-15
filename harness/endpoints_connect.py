"""endpoints_connect.py -- connect to a loopback upstream without the Windows timer wait.

A Python socket that has a timeout connects without blocking and then waits
until the socket is writable. On Windows that wait returns about 15 ms late,
one timer tick, for a connect that finished at once. Measured on Windows 11
with Python 3.12.10 on 2026-11-15, 300 loopback connects each way, twice:

  with a timeout     median 0.3 to 0.5 ms, 78 and 142 of 300 took over 5 ms
                     (p90 15 ms, slowest 23 ms)
  blocking connect   median 0.1 ms, 0 of 300 over 5 ms (slowest 0.5 ms)

A model server on the same machine (Ollama, LM Studio, vLLM, the gateway's
own stub in the overhead gate) is a loopback upstream, and every call opens
one connection, so a quarter to a half of those calls lost a tick before
their first byte.

`create_connection` is `socket.create_connection` with one change: on
Windows, for a loopback address and a real timeout, the connect is made
blocking and the timeout is put on the socket after it. A loopback connect
does not wait on a network: it completes, or the operating system refuses it,
with or without a timeout. Reads and writes keep the timeout. Every other
host, and every other system, connects as before.

`Handler` is the urllib handler that uses it for http:// URLs
(endpoints_http). https:// is unchanged: a TLS upstream is not a loopback
model server in any setup this was measured on.
"""
from __future__ import annotations

import http.client
import ipaddress
import os
import socket
import urllib.request

WINDOWS = os.name == "nt"


def loopback(host: str) -> bool:
    """Is `host` the local machine by name or by address (127.0.0.0/8, ::1)?"""
    name = (host or "").strip("[]").lower()
    if name == "localhost":
        return True
    try:
        return ipaddress.ip_address(name).is_loopback
    except ValueError:
        return False


def create_connection(address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None):
    """`socket.create_connection`, with a blocking connect to loopback on Windows."""
    host, port = address
    prompt = (WINDOWS and loopback(host) and isinstance(timeout, (int, float))
              and not isinstance(timeout, bool) and timeout > 0)
    if not prompt:
        return socket.create_connection(address, timeout, source_address)
    last = None
    for family, kind, proto, _name, where in socket.getaddrinfo(
            host, port, 0, socket.SOCK_STREAM):
        sock = None
        try:
            sock = socket.socket(family, kind, proto)
            if source_address:
                sock.bind(source_address)
            sock.connect(where)         # no timeout yet: returns when the connect is done
            sock.settimeout(timeout)    # reads and writes are bounded as before
            return sock
        except OSError as exc:
            last = exc
            if sock is not None:
                sock.close()
    raise last if last is not None else OSError(f"no address found for {host!r}")


class _Connection(http.client.HTTPConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = create_connection


class Handler(urllib.request.HTTPHandler):
    """urllib's http handler, connecting through `create_connection`."""

    def http_open(self, req):
        return self.do_open(_Connection, req)

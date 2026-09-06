"""egress_route.py -- one endpoint per confined run, made per backend.

`egress_policy` says which hosts a run may reach and `egress_proxy` enforces
it. Neither knows how a confined process is supposed to arrive. That differs
by backend and it is the only part of this feature that does.

  darwin  Seatbelt is a policy over the host's own network stack, so the
          confined process already shares 127.0.0.1 with the proxy. The
          profile allows outbound TCP to one port and denies the rest.

  linux   bubblewrap gives the run a network namespace with nothing in it
          but its own loopback, so a host port is unreachable by
          construction. A pathname unix socket is scoped to the filesystem
          rather than to the namespace, so the proxy listens on one in the
          scratch directory, which the run already has bind-mounted
          writable, and `egress_bridge` runs inside to offer the TCP port
          the confined command knows how to use.

A route that cannot be made is refused rather than downgraded. The caller's
fallback is a run with no network, which is what it had before this existed
and is honest about. Falling back to an open network instead would hand a
run more than it asked for at the moment the narrow path failed.
"""
from __future__ import annotations

import os
import socket
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

from .egress_policy import EgressPolicy
from .egress_proxy import EgressProxy, serve

SCHEMA = "flywheel.egress-route/v1"

#: The unix socket's name inside the scratch directory.
SOCKET_NAME = "egress.sock"

#: How much of `sockaddr_un.sun_path` a path may use. The kernel field is
#: 108 bytes on Linux and a longer path is truncated rather than refused,
#: which would bind a socket nobody can name. The margin is for the name.
SUN_PATH_LIMIT = 100


class RouteUnavailable(RuntimeError):
    """No endpoint can be made for this backend on this host."""


@dataclass(frozen=True)
class EgressRoute:
    """Where a confined run sends its connections, and what it may ask for."""

    backend: str
    #: What the host listens on: an address and port, or a socket path.
    endpoint: str
    #: The TCP port the confined process dials. On Linux this is inside the
    #: namespace and is not a port on the host at all.
    port: int
    hosts: tuple = ()
    ports: tuple = ()

    def record(self) -> dict:
        return {"schema": SCHEMA, "backend": self.backend,
                "endpoint": self.endpoint, "port": self.port,
                "hosts": list(self.hosts), "ports": list(self.ports)}

    def env(self) -> dict:
        """The proxy variables a confined command reads.

        Both schemes point here. A cleartext request is refused by the proxy
        with a reason, and leaving `HTTP_PROXY` unset would instead make it
        a connection that goes nowhere and times out, which is the same
        outcome described worse. `NO_PROXY` is emptied because an inherited
        one is a list of hosts this route would otherwise be told to skip.
        """
        where = f"http://127.0.0.1:{self.port}"
        return {"HTTP_PROXY": where, "HTTPS_PROXY": where,
                "http_proxy": where, "https_proxy": where,
                "ALL_PROXY": where, "all_proxy": where, "NO_PROXY": ""}


def bridge_argv(route: EgressRoute, python: str | None = None) -> list:
    """What has to run inside a Linux namespace before the command does.

    `--ro-bind / /` leaves both the interpreter and this repository readable
    inside the sandbox at the paths they have outside, so the bridge is
    named by absolute path rather than imported.
    """
    bridge = Path(__file__).resolve().parent / "egress_bridge.py"
    return [python or sys.executable, str(bridge),
            "--socket", route.endpoint, "--port", str(route.port), "--"]


def _free_port() -> int:
    """A port number nothing is using at the moment it is asked for."""
    sock = socket.socket()
    try:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
    finally:
        sock.close()


def fits_sun_path(path) -> bool:
    """Whether a socket at this path would still be named by this path.

    `bind` truncates rather than refusing, so a path over the limit produces
    a socket nobody can reach under the name that was asked for. The length
    counted is bytes rather than characters, because a non-ASCII directory
    name spends more than one byte per character in the field.
    """
    return len(str(path).encode("utf-8")) <= SUN_PATH_LIMIT


def _unix_listener(scratch) -> tuple:
    """A pathname socket in the scratch directory, and its path."""
    if not hasattr(socket, "AF_UNIX"):
        raise RouteUnavailable("this host has no pathname unix sockets")
    path = str(Path(scratch) / SOCKET_NAME)
    if not fits_sun_path(path):
        raise RouteUnavailable(
            f"scratch path is too long for a unix socket: {len(path)} bytes")
    try:
        os.unlink(path)
    except OSError:
        pass
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        listener.bind(path)
        listener.listen(16)
    except OSError as exc:
        listener.close()
        raise RouteUnavailable(f"cannot listen on {path}: {exc}") from exc
    return listener, path


def _tcp_listener() -> tuple:
    """A loopback listener the confined process can reach directly."""
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        listener.bind(("127.0.0.1", 0))
        listener.listen(16)
    except OSError as exc:
        listener.close()
        raise RouteUnavailable(f"cannot listen on loopback: {exc}") from exc
    port = listener.getsockname()[1]
    return listener, f"127.0.0.1:{port}", port


class OpenRoute:
    """A running proxy and the route to it, for the length of one run.

    Closing is not optional and not deferred to a finaliser. The listener is
    a way into a policy that has stopped applying the moment the run is
    over, so it is shut before the record is written.
    """

    def __init__(self, route: EgressRoute, proxy: EgressProxy, listener,
                 stop: threading.Event, thread: threading.Thread,
                 socket_path: str | None = None):
        self.route = route
        self.proxy = proxy
        self._listener = listener
        self._stop = stop
        self._thread = thread
        self._socket_path = socket_path

    def record(self) -> dict:
        """The route and every request that crossed it, refusals included."""
        out = self.route.record()
        out["attempts"] = self.proxy.record()["attempts"]
        return out

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)
        try:
            self._listener.close()
        except OSError:
            pass
        if self._socket_path:
            try:
                os.unlink(self._socket_path)
            except OSError:
                pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def open_route(policy: EgressPolicy, backend: str, scratch, *,
               proxy=None) -> OpenRoute:
    """Start the host side of the route for one run.

    `proxy` is injectable so a caller can supply one with resolution and
    dialling of its own, which is how the route is exercised without asking
    the network anything.
    """
    served = proxy if proxy is not None else EgressProxy(policy)
    if backend == "bwrap":
        listener, path = _unix_listener(scratch)
        endpoint, port, socket_path = path, _free_port(), path
    elif backend == "seatbelt":
        listener, endpoint, port = _tcp_listener()
        socket_path = None
    else:
        raise RouteUnavailable(f"no route for backend: {backend}")
    stop = threading.Event()
    thread = threading.Thread(target=serve, args=(served, listener, stop),
                              daemon=True)
    thread.start()
    route = EgressRoute(backend=backend, endpoint=endpoint, port=port,
                        hosts=policy.hosts, ports=policy.ports)
    return OpenRoute(route, served, listener, stop, thread, socket_path)

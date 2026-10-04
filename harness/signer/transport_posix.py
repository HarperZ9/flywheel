"""transport_posix.py -- the signer's Unix socket, and who is on the other end.

The socket lives in a directory the signer user owns (``/run/flywheel-signer``
in the shipped setup), so the agent can connect but cannot replace the socket
with its own. The caller's uid comes from the kernel: ``SO_PEERCRED`` on Linux,
``LOCAL_PEERCRED`` on macOS. Where neither is available the identity is
reported as unattested; the signer never guesses.
"""
from __future__ import annotations

import os
import socket
import socketserver
import struct
import sys

from . import wire
from .statement import SAME, SEPARATE, UNATTESTED


def peer_uid(sock) -> int | None:
    """The connecting process's uid, from the kernel, or None."""
    if hasattr(socket, "SO_PEERCRED"):
        raw = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED,
                              struct.calcsize("3i"))
        return struct.unpack("3i", raw)[1]
    if sys.platform == "darwin":
        try:
            raw = sock.getsockopt(0, 0x001, 76)   # SOL_LOCAL, LOCAL_PEERCRED
            return struct.unpack("II", raw[:8])[1]
        except OSError:
            return None
    return None


def isolation_for(uid: int | None) -> dict:
    me = os.geteuid()
    if uid is None:
        return {"mode": UNATTESTED, "signer": f"uid:{me}", "client": "unknown",
                "via": "no kernel peer credential on this platform"}
    mode = SEPARATE if uid != me else SAME
    return {"mode": mode, "signer": f"uid:{me}", "client": f"uid:{uid}",
            "via": "kernel peer credential"}


def serve(address: str, handle, ready=None) -> None:
    """Serve forever. ``handle(request, isolation) -> response``."""
    if os.path.exists(address):
        if os.stat(address).st_uid != os.geteuid():
            raise RuntimeError(f"{address} exists and is owned by someone else")
        os.unlink(address)

    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            try:
                req = wire.decode_from(self.request.recv)
                iso = isolation_for(peer_uid(self.request))
                self.request.sendall(wire.encode(handle(req, iso)))
            except wire.WireError:
                return

    with socketserver.ThreadingUnixStreamServer(address, Handler) as srv:
        os.chmod(address, 0o666)   # access is governed by the directory
        if ready:
            ready()
        srv.serve_forever()


def call(address: str, request: dict, timeout: float = 5.0) -> dict:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect(address)
        s.sendall(wire.encode(request))
        return wire.decode_from(s.recv)

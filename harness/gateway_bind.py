"""A gateway listener no other socket can share (N-23, N-24).

`ThreadingHTTPServer` sets SO_REUSEADDR, which on Windows lets a second
socket bind the same port while the gateway listens (experiment X3), so a
same-user process could take the port and collect what hooks send. On
Windows this server clears `allow_reuse_address` and sets
SO_EXCLUSIVEADDRUSE before binding; X3 showed both halves are needed, since
the exclusive flag with reuse still on fails the bind with WinError 10022.
POSIX keeps SO_REUSEADDR, which there does not let a second socket take an
active listener. `oauth_callback.py` uses the same pattern.
"""
from __future__ import annotations

from http.server import ThreadingHTTPServer
import socket
import sys


class ExclusiveThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = sys.platform != "win32"

    def server_bind(self):
        if sys.platform == "win32":
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

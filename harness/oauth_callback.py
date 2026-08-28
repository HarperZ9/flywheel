"""oauth_callback.py -- the hardened loopback listener for a sign-in redirect.

A loopback redirect (RFC 8252 s7.3) shares 127.0.0.1 with every other process
on the machine, so the channel is treated as hostile:

  - the port is bound exclusively, so no second process can co-bind it,
  - the callback path carries a per-run nonce compared in constant time; a
    request that does not match gets 404 and the listener keeps waiting,
  - a captured code is never overwritten, so a later stray request cannot
    clobber or blank it,
  - only a matching request with a code stops the listener, so an unrelated
    local GET cannot abort the sign-in,
  - the socket is closed on every exit path.

The authorization code alone is not enough to redeem anything: the PKCE
verifier never leaves the signing-in process.
"""
from __future__ import annotations

import secrets
import socket
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional

_OK_BODY = b"Signed in. You can close this tab and return to flywheel."
_DENIED_BODY = b"Sign-in was denied or carried no authorization code."
_STRAY_BODY = b"Not found."


class CallbackServer(HTTPServer):
    """One-shot loopback listener on an ephemeral port with a nonce path."""

    # Never let another process co-bind this port (the default 1 permits it).
    allow_reuse_address = False

    def __init__(self, advertise_host: Optional[str] = None):
        self.nonce = secrets.token_urlsafe(16)
        self.code: Optional[str] = None
        self.error: Optional[str] = None
        self._captured = threading.Event()
        # A local sign-in keeps loopback: the browser and the engine share the
        # machine. A phone reaches a paired engine over the network, so a
        # remote sign-in binds every interface and advertises the address the
        # phone can reach. The guard is the same on both paths: a 128-bit
        # nonce path, constant-time match, one-shot capture, and a code that
        # is useless without the PKCE verifier, which never leaves this
        # process. Absent an advertise host, nothing changes.
        self.advertise_host = advertise_host or "127.0.0.1"
        bind_host = "0.0.0.0" if advertise_host else "127.0.0.1"
        super().__init__((bind_host, 0), _CallbackHandler)

    def server_bind(self):
        # Windows honors SO_REUSEADDR as "steal the port"; SO_EXCLUSIVEADDRUSE
        # is the flag that actually forbids a second bind.
        if sys.platform == "win32":
            try:
                self.socket.setsockopt(socket.SOL_SOCKET,
                                       socket.SO_EXCLUSIVEADDRUSE, 1)
            except (OSError, AttributeError):
                pass
        super().server_bind()

    @property
    def callback_url(self) -> str:
        return (f"http://{self.advertise_host}:{self.server_address[1]}"
                f"/cb/{self.nonce}")

    def path_matches(self, path: str) -> bool:
        given = urllib.parse.urlparse(path).path
        return secrets.compare_digest(given, f"/cb/{self.nonce}")

    def capture(self, code: Optional[str], error: Optional[str]) -> None:
        """First matching result wins; a later request can never clobber it."""
        if self._captured.is_set():
            return
        self.code, self.error = code, error
        self._captured.set()

    def wait_for_code(self, timeout: float) -> Optional[str]:
        """Serve until the nonce path answers or the timeout expires. Always
        closes the socket."""
        thread = threading.Thread(target=self.serve_forever, daemon=True)
        thread.start()
        try:
            self._captured.wait(timeout)
        finally:
            self.shutdown()
            thread.join(5)
            self.server_close()
        return self.code


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 (http.server API)
        if not self.server.path_matches(self.path):
            self._respond(404, _STRAY_BODY)   # keep serving: this was not ours
            return
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        code = (params.get("code") or [None])[0]
        error = (params.get("error") or [None])[0]
        self.server.capture(code, error)
        self._respond(200 if code else 400, _OK_BODY if code else _DENIED_BODY)
        threading.Thread(target=self.server.shutdown, daemon=True).start()

    def _respond(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        # Codes and tokens must never reach stderr.
        pass

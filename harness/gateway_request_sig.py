"""Gateway side of the capture channel: hello proofs and signed requests (7.1).

The hello answers a client nonce with a fresh server nonce and a proof bound
to the address this gateway bound, and nothing else; it is rate-limited to 20
per second. A signed request is accepted only on `/api/traces/capture/*`,
only when its time is within 60 seconds, its server nonce was issued by this
process within 120 seconds, and its client nonce was not seen in the last 120
seconds. The raw token never crosses the socket, so a proxy or a transport log
learns no reusable credential. Against same-user code this gives nothing,
since that code can read the token (design 3.5).
"""
from __future__ import annotations

import secrets
import threading
import time

from .capture_hooks import protocol

SKEW_S = 60
NONCE_TTL_S = 120
HELLO_PER_SECOND = 20


class ChannelState:
    """In-memory nonce bookkeeping for one gateway process."""

    def __init__(self, clock=time.time) -> None:
        self.clock = clock
        self.lock = threading.Lock()
        self.issued: dict[str, float] = {}
        self.seen: dict[str, float] = {}
        self.window: list[float] = []

    def _prune(self, now: float) -> None:
        for table in (self.issued, self.seen):
            for key in [k for k, t in table.items() if now - t > NONCE_TTL_S]:
                del table[key]

    def hello(self, token: str, cn: str, host: str, port: int) -> dict | None:
        """The hello body, or None when rate-limited or the nonce is malformed."""
        if not protocol.is_nonce(cn):
            return None
        now = self.clock()
        with self.lock:
            self.window = [t for t in self.window if now - t < 1.0]
            if len(self.window) >= HELLO_PER_SECOND:
                return None
            self.window.append(now)
            self._prune(now)
            sn = secrets.token_hex(16)
            self.issued[sn] = now
        k_s, _ = protocol.derive_keys(token)
        return {"schema": "flywheel.capture-hello/v1", "sn": sn,
                "proof": protocol.server_proof(k_s, cn, sn, host, port)}

    def verify(self, token: str, header: str, method: str, path: str, body: bytes,
               host: str, port: int) -> bool:
        fields = protocol.parse_header(header or "")
        if fields is None or not token or not path.startswith(protocol.PREFIX):
            return False
        now = self.clock()
        if abs(now - fields["ts"]) > SKEW_S:
            return False
        _, k_c = protocol.derive_keys(token)
        expected = protocol.signature(k_c, method, path, body, fields["ts"],
                                      fields["nonce"], fields["sn"], host, port)
        if not protocol.same(expected, fields["sig"]):
            return False
        with self.lock:
            self._prune(now)
            issued = self.issued.get(fields["sn"])
            if issued is None or now - issued > NONCE_TTL_S or fields["nonce"] in self.seen:
                return False
            self.seen[fields["nonce"]] = now
        return True


STATE = ChannelState()

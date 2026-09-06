"""lsp_connection.py -- one LSP peer over a pair of byte streams.

The peer itself is harness/jsonrpc_peer.py, shared with the ACP client. What is
here is the binding of that peer to LSP's Content-Length framing, and the names
the rest of the LSP modules import from.

LSP is asymmetric in a way ACP is not: the server sends requests back at the
client (configuration, progress creation, registration) and it sends
notifications nobody asked for (diagnostics, log messages). Both arrive on the
reader thread whether or not this side is waiting on anything, which is why the
client keeps a handler rather than reading only inside a request.
"""
from __future__ import annotations

from typing import BinaryIO

from .jsonrpc_peer import (RECEIVED, SENT, ConnectionClosed, Handler,
                           InvalidParams, MethodNotFound, Observer, Peer,
                           PeerError, RejectAll)
from .lsp_wire import LspFraming

__all__ = ["Connection", "ConnectionClosed", "Handler", "InvalidParams",
           "MethodNotFound", "Observer", "PeerError", "RECEIVED", "RejectAll",
           "SENT"]


class Connection(Peer):
    """A live LSP peer. Start it, call it, stop it."""

    def __init__(self, outgoing: BinaryIO, incoming: BinaryIO, *,
                 handler: Handler | None = None,
                 observer: Observer | None = None) -> None:
        super().__init__(outgoing, incoming, framing=LspFraming(),
                         handler=handler, observer=observer, name="lsp")

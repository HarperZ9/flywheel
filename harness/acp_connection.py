"""acp_connection.py -- one ACP peer over a pair of byte streams.

Both sides of ACP speak the same JSON-RPC dialect and differ only in which
methods they answer, so this layer is direction-agnostic. A Flywheel client
driving Claude Code and a Flywheel agent driven by an editor are the same
Connection with a different handler.

The peer itself is harness/jsonrpc_peer.py, shared with the LSP client. What is
here is the binding of that peer to ACP's newline framing, and the names the
rest of the ACP modules import from. Everything a caller of this module used
before the peer was extracted still comes from this module.
"""
from __future__ import annotations

from typing import BinaryIO

from .acp_wire import AcpFraming
from .jsonrpc_peer import (RECEIVED, SENT, ConnectionClosed, Handler,
                           InvalidParams, MethodNotFound, Observer, Peer,
                           PeerError, RejectAll)

__all__ = ["Connection", "ConnectionClosed", "Handler", "InvalidParams",
           "MethodNotFound", "Observer", "PeerError", "RECEIVED", "RejectAll",
           "SENT"]


class Connection(Peer):
    """A live ACP peer. Start it, call it, stop it."""

    def __init__(self, outgoing: BinaryIO, incoming: BinaryIO, *,
                 handler: Handler | None = None,
                 observer: Observer | None = None) -> None:
        super().__init__(outgoing, incoming, framing=AcpFraming(),
                         handler=handler, observer=observer, name="acp")

"""lsp_incoming.py -- what a language server sends without being asked.

LSP is not a client asking and a server answering. The server opens requests of
its own and pushes notifications whenever it likes, and a client that only
listens while a call is outstanding either misses them or deadlocks waiting for
a reply the server is waiting on it to unblock.

Two of the answers here are load-bearing. A server that asked for configuration
and got method-not-found may fall back to defaults or may simply wait, so the
documented shape gets sent: one null per requested item, meaning no settings for
that section. Progress creation is answered because the client declared window
progress, and a declared capability that then refuses is worse than one never
claimed.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .lsp_connection import MethodNotFound
from .lsp_documents import Documents

__all__ = ["Published", "ServerHandler", "published_from"]


@dataclass
class Published:
    """One publishDiagnostics notification, as the client received it.

    `current` is None rather than True when the server published without a
    version. Not knowing is not the same as knowing the set is fresh, and a
    client reporting True there would be inventing the one fact the field exists
    to carry.

    `model` says how the set was come by, because an empty one means different
    things either way. Pushed, it is the last thing a server chose to say.
    Pulled, it is what the server answered when asked.
    """

    uri: str
    items: list = field(default_factory=list)
    version: int | None = None
    current: bool | None = None
    model: str = "push"


def published_from(params: dict, documents: Documents) -> Published:
    """Read one diagnostics notification against the buffer it names."""
    uri = params.get("uri", "")
    version = params.get("version")
    stamped = isinstance(version, int) and not isinstance(version, bool)
    return Published(
        uri=uri, items=list(params.get("diagnostics") or []),
        version=version if stamped else None,
        current=documents.is_current(uri, version) if stamped else None)


class ServerHandler:
    """Answers what a language server asks of its client, and nothing else."""

    def __init__(self, client) -> None:
        self._client = client

    def on_request(self, method: str, params: dict) -> object:
        if method == "workspace/configuration":
            return [None for _ in ((params or {}).get("items") or [None])]
        if method == "window/workDoneProgress/create":
            return None
        if method in ("client/registerCapability",
                      "client/unregisterCapability"):
            # Declined in the declared capabilities, so this should not arrive.
            # Recorded rather than refused: a server that registers anyway is a
            # fact about the run, not an error in it.
            self._client.registrations.append({"method": method,
                                               "params": params})
            return None
        if method == "workspace/workspaceFolders":
            return self._client.workspace_folders()
        raise MethodNotFound(method)

    def on_notification(self, method: str, params: dict) -> None:
        if method == "textDocument/publishDiagnostics":
            self._client.accept_diagnostics(params or {})
        elif method in ("window/logMessage", "window/showMessage"):
            self._client.messages.append(params or {})

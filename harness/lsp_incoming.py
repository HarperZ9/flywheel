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

`workspace/applyEdit` is the one request that writes. It is routed to the client
so the decision lives with the object holding the workspace root and the write
flag, and it is answered rather than raised even when refused, because the
reply has a field for saying no and an error does not.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .lsp_connection import MethodNotFound
from .lsp_documents import Documents
from .lsp_edits import EditRefused, apply_plan, plan_edit

__all__ = ["Published", "ServerHandler", "answer_apply_edit", "published_from"]


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


def answer_apply_edit(client, params: dict) -> dict:
    """Apply a WorkspaceEdit a server pushed, or say why not.

    Three gates, in the order that costs least. The client has to have been
    told it may write, since a client that never claimed applyEdit should not
    start doing it. It has to know its workspace root, because with no root
    there is nothing to check a URI against and every path is inside. Then the
    edit itself has to survive planning.

    Buffers this client has open are replaced afterwards so the server is told
    what the files now hold. Without that the next request is answered against
    text the server thinks is still there and this client has already changed.
    """
    if not getattr(client, "apply_edit", False):
        return {"applied": False,
                "failureReason": "write-not-allowed: this client did not "
                                 "declare workspace/applyEdit"}
    if client.root is None:
        return {"applied": False,
                "failureReason": "outside-root: this client has no workspace "
                                 "root to contain the edit"}
    try:
        plan = plan_edit((params or {}).get("edit") or {}, root=client.root,
                         encoding=client.encoding, documents=client.documents)
        summary = apply_plan(plan, allow_write=True)
    except EditRefused as e:
        client.edit_records.append({"applied": False, "reason": e.reason,
                                    "detail": e.detail})
        return {"applied": False, "failureReason": str(e)}
    for change in plan.files:
        if change.changed() and change.uri in client.documents:
            client.replace(change.uri, change.after)
    client.edit_records.append(summary)
    return {"applied": True}


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
        if method == "workspace/applyEdit":
            # Answered rather than raised, in both directions. A server told no
            # can carry on; a server whose request errored may not, and there is
            # a field in the reply for exactly this.
            return answer_apply_edit(self._client, params or {})
        raise MethodNotFound(method)

    def on_notification(self, method: str, params: dict) -> None:
        if method == "textDocument/publishDiagnostics":
            self._client.accept_diagnostics(params or {})
        elif method in ("window/logMessage", "window/showMessage"):
            self._client.messages.append(params or {})

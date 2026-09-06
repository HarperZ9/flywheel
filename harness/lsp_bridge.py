"""lsp_bridge.py -- the editor surface, over the LSP client that replaced it.

This file used to be the whole implementation: its own framing, its own request
loop, one lock held across a blocking read, and three methods. That work moved
into harness/lsp_client.py and the modules under it, which speak the lifecycle
the specification defines, negotiate a position encoding, read the server's
capabilities before sending, and stamp every answer with the document version it
was asked at.

What stays here is the surface. The gateway route, the Flutter editor, and
harness/lsp_diagnostics.py all call these names with these argument orders, and
a rewrite that also renamed things would have been two changes landing as one.
New callers should use LspClient directly; it says more than this shape can
carry, starting with whether an answer is still about the file you are holding.

The three-method whitelist is this file's own and it stays. It is what makes a
bad method name a refusal here rather than a request going out to a server that
may or may not answer it.
"""
from __future__ import annotations

import atexit
import threading
from pathlib import Path

from .lsp_client import LspClient
from .lsp_connection import ConnectionClosed, PeerError
from .lsp_documents import to_uri
from .lsp_pull import PULL, published_from_report

#: Shorter than the client's own default. An editor keystroke that has not been
#: answered in fifteen seconds has stopped being useful to the person typing.
_TIMEOUT = 15.0

#: What this surface offers. Deliberately smaller than what the client can ask.
_METHODS = ("definition", "references", "hover")

#: Kept under its old name because harness/lsp_diagnostics.py imports it, and
#: bound to the client's own builder so the two cannot drift into producing
#: different strings for one path. A lookup keyed on a URI the client never
#: wrote reads as a file with nothing to say about it.
_uri = to_uri


class LSPError(Exception):
    pass


class LSPBridge:
    """One running language server, initialized against a workspace root."""

    def __init__(self, command: list, root: str):
        self.command = list(command)
        self.root = str(Path(root).resolve())
        try:
            self._client = LspClient.start(self.command, root=self.root)
        except (OSError, ValueError) as e:
            raise LSPError(f"language server did not start: {e}") from e
        try:
            self._client.initialize(timeout=_TIMEOUT)
        except (ConnectionClosed, PeerError, TimeoutError, OSError) as e:
            self._client.close()
            raise LSPError(f"language server did not initialize: {e}") from e

    @property
    def _proc(self):
        """The child process, under the name this file used to hold it by."""
        return self._client.process

    @property
    def diagnostics(self) -> dict:
        """uri -> the last published list, flattened out of the client's record.

        The client keeps the version each set was published against and whether
        it still describes the current buffer. This shape drops both, because
        the callers of this surface have never had them.
        """
        return {uri: entry.items
                for uri, entry in self._client.published.items()}

    def sync_buffer(self, path: str, text: str, language_id: str) -> None:
        """didOpen on first sight, didChange after, so the server sees the live
        buffer including edits that were never saved."""
        self._client.sync(path, text, language_id)

    def published(self, path: str):
        """The diagnostics for one buffer, however this server hands them out.

        A server that advertised a diagnostic provider is asked. One that did
        not is fenced, because pushing is the only way it says anything. The
        returned set carries which of the two happened, so a caller can tell an
        empty answer from an absent one.
        """
        uri = _uri(path)
        if self._client.supports(PULL):
            try:
                return published_from_report(
                    self._client.ask(PULL, uri, timeout=_TIMEOUT))
            except (ConnectionClosed, PeerError, TimeoutError, OSError) as e:
                raise LSPError(str(e)) from e
        self.query("hover", path, 0, 0)
        return self._client.diagnostics(uri)

    def query(self, method: str, path: str, line: int, character: int):
        if method not in _METHODS:
            raise LSPError(f"unknown method '{method}'")
        try:
            answer = self._client.ask(method, _uri(path), line=int(line),
                                      character=int(character),
                                      timeout=_TIMEOUT)
        except (ConnectionClosed, PeerError, TimeoutError, OSError) as e:
            raise LSPError(str(e)) from e
        # A null result becomes an empty mapping, which is what this surface has
        # always returned and what the Flutter side reads. Callers who need to
        # tell "the server has no answer" from "the server answered nothing"
        # should be asking the client, which keeps them apart.
        return answer.result or {}

    def alive(self) -> bool:
        return self._client.alive()

    def close(self) -> None:
        try:
            self._client.close()
        except OSError:
            pass


_BRIDGES: dict = {}
_BRIDGES_LOCK = threading.Lock()


def close_all() -> int:
    """Kill every cached server and forget it. Returns how many were closed.

    The cache is keyed by (command, root) and deliberately outlives any single
    call, which is what makes a second query fast. Nothing was ending those
    processes, so every distinct key leaked a language server for the life of
    the interpreter. A long-lived caller accumulated them silently; a test
    session left them behind after it exited.
    """
    with _BRIDGES_LOCK:
        bridges = list(_BRIDGES.values())
        _BRIDGES.clear()
    for bridge in bridges:
        try:
            bridge.close()
        except Exception:
            pass                      # shutting down; a stuck server is not news
    return len(bridges)


# A cache that outlives its callers has to clean up after itself, because the
# callers by definition are not around to do it.
atexit.register(close_all)


def get_bridge(command: list, root: str) -> "LSPBridge":
    """The shared (command, root) bridge, started on first use."""
    key = (tuple(command), str(Path(root).resolve()))
    with _BRIDGES_LOCK:
        bridge = _BRIDGES.get(key)
        if bridge is None or not bridge.alive():
            bridge = LSPBridge(command, root)
            _BRIDGES[key] = bridge
        return bridge


def lsp_query(command: list, root: str, file: str, text: str,
              language_id: str, method: str, line: int, character: int) -> dict:
    """One editor query: reuse (or start) the server for (command, root),
    sync the live buffer, ask, and return locations/hover as plain JSON."""
    if not isinstance(command, list) or not command:
        return {"error": "provide the language server 'command' as argv"}
    if not Path(root).is_dir():
        return {"error": f"root is not an existing directory: {root}"}
    try:
        bridge = get_bridge(command, root)
        bridge.sync_buffer(file, text, language_id)
        result = bridge.query(method, file, line, character)
        return {"schema": "flywheel.lsp/v1", "method": method,
                "result": result}
    except LSPError as e:
        return {"error": str(e)}
    except (OSError, ValueError) as e:
        return {"error": f"{type(e).__name__}: {e}"}

"""lsp_client.py -- drive a language server as a subprocess and keep the record.

Flywheel already had an LSP bridge that answered three requests. This is the
same idea taken seriously: the lifecycle the specification defines, the position
encoding both sides agreed on, the capability answer read before a request goes
out, and a version stamped on every answer so a reader can tell whether it still
describes the file.

That last part is worth spelling out. An LSP request names a document and
carries no version, so a reply landing after an edit is about text nobody is
looking at. A server has ContentModified for the cases it notices and nothing
for the cases it does not. This client stamps the version itself, once when the
request goes out and again when the answer arrives, and says plainly when the
two differ. An answer that was true and is now stale is a different thing from
an answer that was wrong, and a record unable to separate them is not worth
keeping.

The server talks back. Configuration requests, progress creation, registration,
log messages and published diagnostics all arrive whether or not this side is
waiting on anything, which is why the reader thread runs continuously rather
than only inside a request.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .child_stdio import settled, spawn, text_of
from .lsp_capabilities import (SYNC_NONE, initialize_params,
                               negotiate_encoding, server_summary, supports,
                               sync_kind, wants_open_close)
from .lsp_connection import (Connection, ConnectionClosed, Observer,
                             PeerError)
from .lsp_documents import Documents, to_uri
from .lsp_incoming import Published, ServerHandler, published_from
from .lsp_operations import method_of, params_for
from .lsp_positions import DEFAULT_ENCODING, character_of, split_lines

#: What a request waits before this side stops waiting. A server indexing a
#: large workspace is slow once, not slow forever, so this covers a cold start
#: and still turns a wedged server into a failure rather than a hang.
DEFAULT_TIMEOUT = 30.0

__all__ = ["Answer", "LspClient", "NotInitialized", "Published",
           "UnsupportedOperation"]


class NotInitialized(RuntimeError):
    """A request was made before initialize was answered."""


class UnsupportedOperation(RuntimeError):
    """The server said it does not answer this request."""


@dataclass(frozen=True)
class Answer:
    """One server reply, and what the document looked like when it was asked.

    `current` is the point of the type. False means the document changed between
    the request going out and the answer landing, so the positions in `result`
    describe text this client no longer holds.
    """

    operation: str
    method: str
    params: dict
    result: object
    stamp: dict
    current: bool
    encoding: str


class LspClient:
    """One language server, from spawn to exit."""

    def __init__(self, connection: Connection, *,
                 process: subprocess.Popen | None = None,
                 root: Path | None = None,
                 stderr: list[bytes] | None = None) -> None:
        self.process = process
        self.root = root
        self.encoding = DEFAULT_ENCODING
        self.capabilities: dict = {}
        self.server_info: dict = {}
        self.registrations: list[dict] = []
        self.messages: list[dict] = []
        self.documents = Documents(DEFAULT_ENCODING)
        self.published: dict[str, Published] = {}
        self.apply_edit = False          # set before initialize() to declare it
        self.edit_records: list[dict] = []
        self._initialized = False
        self._stderr = stderr if stderr is not None else []
        self._conn = connection
        connection.handler = ServerHandler(self)

    @classmethod
    def start(cls, argv: Sequence[str], *, root: Path | str | None = None,
              observer: Observer | None = None,
              env: dict[str, str] | None = None) -> "LspClient":
        """Start a language server and connect to its stdio."""
        directory = Path(root or Path.cwd()).resolve()
        process, collected = spawn(argv, directory, env=env, name="lsp")
        connection = Connection(process.stdin, process.stdout,
                                observer=observer)
        client = cls(connection, process=process, root=directory,
                     stderr=collected)
        connection.start()
        return client

    def __enter__(self) -> "LspClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # -- lifecycle -----------------------------------------------------------

    def initialize(self, *, client_name: str = "flywheel",
                   client_version: str = "0",
                   initialization_options: dict | None = None,
                   timeout: float = DEFAULT_TIMEOUT) -> dict:
        """Negotiate, then say so. Nothing may be requested before this returns.

        The encoding is settled here and nowhere else. A server answering with
        one this client cannot convert raises, because reading the wrong span of
        every file while reporting success is worse than not running.
        """
        root_uri = to_uri(self.root) if self.root is not None else None
        result = self._conn.call("initialize", initialize_params(
            root_uri, process_id=os.getpid(), client_name=client_name,
            client_version=client_version, apply_edit=self.apply_edit,
            initialization_options=initialization_options), timeout=timeout)
        result = result if isinstance(result, dict) else {}
        self.encoding = negotiate_encoding(result)
        self.documents.encoding = self.encoding
        self.capabilities = result.get("capabilities") or {}
        self.server_info = result.get("serverInfo") or {}
        self._conn.notify("initialized", {})
        self._initialized = True
        return result

    def summary(self) -> dict:
        """What the server said about itself, in the shape a record carries."""
        return server_summary({"capabilities": self.capabilities,
                               "serverInfo": self.server_info})

    def supports(self, operation: str) -> bool:
        """Whether the server advertised the request this operation makes."""
        return supports({"capabilities": self.capabilities},
                        method_of(operation))

    def workspace_folders(self) -> list | None:
        if self.root is None:
            return None
        return [{"uri": to_uri(self.root), "name": self.root.name or "root"}]

    def shutdown(self, timeout: float = DEFAULT_TIMEOUT) -> None:
        """The ordered exit: release documents, shutdown, exit.

        Documents go first so the server is not holding a client's copy of a
        file it is about to stop tracking. A server that never answers shutdown
        is killed by `close`, which is why nothing here raises.
        """
        try:
            for params in self.documents.close_all():
                self._conn.notify("textDocument/didClose", params)
            self._conn.call("shutdown", None, timeout=timeout)
            self._conn.notify("exit", None)
        except (ConnectionClosed, PeerError, TimeoutError, OSError):
            return

    def close(self, grace: float = 5.0) -> None:
        """Stop the server, politely if it is still listening.

        Closing the child's stdin is what ends a stdio server that never got a
        shutdown: it reads end-of-file and returns on its own. Without that it
        sits waiting for a message nobody is going to send, and every close
        costs the full grace period before turning into a kill.
        """
        self._conn.close()
        process = self.process
        if process is None:
            return
        try:
            if process.stdin is not None:
                process.stdin.close()
        except OSError:
            pass
        try:
            process.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=grace)

    def alive(self) -> bool:
        """Whether the server process is still running."""
        return self.process is not None and self.process.poll() is None

    def stderr_text(self) -> str:
        """Whatever the server wrote to its own error stream, bounded.

        A dead child is waited on first, because the last thing it wrote is
        usually the reason it is dead and the read that misses it reads clean.
        """
        if self.process is not None and self.process.poll() is not None:
            settled(self.process)
        return text_of(self._stderr)

    # -- documents -----------------------------------------------------------

    def open(self, path: str | Path, language_id: str,
             text: str | None = None) -> str:
        """Take ownership of a file and tell the server. Returns its URI."""
        location = Path(path)
        uri = to_uri(location)
        if text is None:
            text = location.read_text(encoding="utf-8")
        params = self.documents.did_open(uri, language_id, text)
        if wants_open_close({"capabilities": self.capabilities}):
            self._conn.notify("textDocument/didOpen", params)
        return uri

    def replace(self, uri: str, text: str) -> int:
        """Send the whole buffer again. Returns the version it now holds."""
        params = self.documents.replace_text(uri, text)
        if sync_kind({"capabilities": self.capabilities}) != SYNC_NONE:
            self._conn.notify("textDocument/didChange", params)
        return params["textDocument"]["version"]

    def close_document(self, uri: str) -> None:
        params = self.documents.did_close(uri)
        if wants_open_close({"capabilities": self.capabilities}):
            self._conn.notify("textDocument/didClose", params)

    def sync(self, path: str | Path, text: str, language_id: str) -> str:
        """Open on first sight and replace after, so the server sees the buffer."""
        uri = to_uri(Path(path))
        if uri in self.documents:
            self.replace(uri, text)
            return uri
        return self.open(path, language_id, text)

    # -- requests ------------------------------------------------------------

    def ask(self, operation: str, uri: str, *,
            timeout: float = DEFAULT_TIMEOUT, strict: bool = False,
            **kwargs) -> Answer:
        """Make one request about one document, and stamp what it was about.

        Characters in `kwargs` are already in the negotiated encoding. Use
        `ask_at` to hand over a Python index and have it converted.
        """
        if not self._initialized:
            raise NotInitialized(f"{operation} before initialize")
        if strict and not self.supports(operation):
            raise UnsupportedOperation(
                f"the server does not answer {method_of(operation)}")
        method = method_of(operation)
        params = params_for(operation, uri, **kwargs)
        stamp = self.documents.stamp(uri)
        result = self._conn.call(method, params, timeout=timeout)
        return Answer(operation=operation, method=method, params=params,
                      result=result, stamp=stamp,
                      current=self.documents.is_current(uri, stamp["version"]),
                      encoding=self.encoding)

    def ask_at(self, operation: str, uri: str, line: int, index: int,
               **kwargs) -> Answer:
        """Ask at a Python string index, converted to the agreed encoding.

        The conversion reads this client's own copy of the document, the same
        text the server was told about, so both sides count over the same
        characters rather than over whatever is on disk.
        """
        lines = split_lines(self.documents.get(uri).text)
        body = lines[line] if 0 <= line < len(lines) else ""
        return self.ask(operation, uri, line=line,
                        character=character_of(body, index, self.encoding),
                        **kwargs)

    # -- what the server sends unasked --------------------------------------

    def accept_diagnostics(self, params: dict) -> None:
        """Store one publishDiagnostics, bound to the version it named."""
        entry = published_from(params, self.documents)
        self.published[entry.uri] = entry

    def diagnostics(self, uri: str) -> Published:
        """What the server last published about this document.

        A document nobody published about reads as an empty set at no version,
        which is the honest shape. It is not a clean file, it is a file the
        server has said nothing about.
        """
        return self.published.get(uri, Published(uri=uri))

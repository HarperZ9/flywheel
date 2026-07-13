"""lsp_bridge.py -- a native Language Server Protocol client over stdio.

Speaks LSP's JSON-RPC framing (Content-Length headers) to any language
server the caller names by argv: `dart language-server`, `pyright-langserver
--stdio`, whatever is installed. The bridge holds one initialized server per
(command, root) pair, sends the editor's live buffer via didOpen/didChange
so unsaved edits are visible, and answers definition, references, and hover.
A missing server is a named error, never a silent fallback. Zero deps."""
from __future__ import annotations

import json
import os
import subprocess
import threading
from pathlib import Path

_TIMEOUT = 15.0


def _uri(path: str) -> str:
    p = Path(path).resolve()
    return p.as_uri()


class LSPError(Exception):
    pass


class LSPBridge:
    """One running language server, initialized against a workspace root."""

    def __init__(self, command: list, root: str):
        self.command = list(command)
        self.root = str(Path(root).resolve())
        self._next_id = 0
        self._lock = threading.Lock()
        self._versions: dict = {}
        try:
            self._proc = subprocess.Popen(
                self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, cwd=self.root)
        except (FileNotFoundError, OSError) as e:
            raise LSPError(f"language server did not start: {e}") from e
        self._request("initialize", {
            "processId": os.getpid(), "rootUri": _uri(self.root),
            "capabilities": {}})
        self._notify("initialized", {})

    # -- framing -----------------------------------------------------------
    def _send(self, msg: dict) -> None:
        body = json.dumps(msg).encode("utf-8")
        frame = b"Content-Length: %d\r\n\r\n%b" % (len(body), body)
        assert self._proc.stdin is not None
        self._proc.stdin.write(frame)
        self._proc.stdin.flush()

    def _read_message(self) -> dict:
        assert self._proc.stdout is not None
        length = None
        while True:
            line = self._proc.stdout.readline()
            if not line:
                raise LSPError("language server closed the stream")
            if line in (b"\r\n", b"\n"):
                break
            if line.lower().startswith(b"content-length:"):
                length = int(line.split(b":", 1)[1].strip())
        if length is None:
            raise LSPError("frame without Content-Length")
        body = self._proc.stdout.read(length)
        return json.loads(body.decode("utf-8", "replace"))

    def _request(self, method: str, params: dict) -> dict:
        with self._lock:
            self._next_id += 1
            rid = self._next_id
            self._send({"jsonrpc": "2.0", "id": rid, "method": method,
                        "params": params})
            # Servers may interleave notifications; read until our id answers.
            timer = threading.Timer(_TIMEOUT, self._proc.kill)
            timer.start()
            try:
                while True:
                    msg = self._read_message()
                    if msg.get("id") == rid:
                        if "error" in msg:
                            raise LSPError(str(msg["error"]))
                        return msg.get("result") or {}
            finally:
                timer.cancel()

    def _notify(self, method: str, params: dict) -> None:
        with self._lock:
            self._send({"jsonrpc": "2.0", "method": method, "params": params})

    # -- editor surface ----------------------------------------------------
    def sync_buffer(self, path: str, text: str, language_id: str) -> None:
        """didOpen on first sight, didChange after: the server always sees
        the editor's live buffer, unsaved edits included."""
        uri = _uri(path)
        version = self._versions.get(uri, 0) + 1
        self._versions[uri] = version
        if version == 1:
            self._notify("textDocument/didOpen", {"textDocument": {
                "uri": uri, "languageId": language_id, "version": version,
                "text": text}})
        else:
            self._notify("textDocument/didChange", {
                "textDocument": {"uri": uri, "version": version},
                "contentChanges": [{"text": text}]})

    def query(self, method: str, path: str, line: int, character: int):
        lsp_method = {
            "definition": "textDocument/definition",
            "references": "textDocument/references",
            "hover": "textDocument/hover",
        }.get(method)
        if lsp_method is None:
            raise LSPError(f"unknown method '{method}'")
        params: dict = {"textDocument": {"uri": _uri(path)},
                        "position": {"line": int(line),
                                     "character": int(character)}}
        if method == "references":
            params["context"] = {"includeDeclaration": True}
        return self._request(lsp_method, params)

    def alive(self) -> bool:
        return self._proc.poll() is None

    def close(self) -> None:
        try:
            self._proc.kill()
        except OSError:
            pass


_BRIDGES: dict = {}
_BRIDGES_LOCK = threading.Lock()


def lsp_query(command: list, root: str, file: str, text: str,
              language_id: str, method: str, line: int, character: int) -> dict:
    """One editor query: reuse (or start) the server for (command, root),
    sync the live buffer, ask, and return locations/hover as plain JSON."""
    if not isinstance(command, list) or not command:
        return {"error": "provide the language server 'command' as argv"}
    if not Path(root).is_dir():
        return {"error": f"root is not an existing directory: {root}"}
    key = (tuple(command), str(Path(root).resolve()))
    try:
        with _BRIDGES_LOCK:
            bridge = _BRIDGES.get(key)
            if bridge is None or not bridge.alive():
                bridge = LSPBridge(command, root)
                _BRIDGES[key] = bridge
        bridge.sync_buffer(file, text, language_id)
        result = bridge.query(method, file, line, character)
        return {"schema": "flywheel.lsp/v1", "method": method,
                "result": result}
    except LSPError as e:
        return {"error": str(e)}
    except (OSError, ValueError) as e:
        return {"error": f"{type(e).__name__}: {e}"}

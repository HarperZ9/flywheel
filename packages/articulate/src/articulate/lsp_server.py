#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
articulate.lsp_server -- a Language Server Protocol server, standard library only.

One server backs VS Code, JetBrains (via LSP4IJ), Neovim, and Sublime. It runs
the deterministic detector on open and on change and publishes diagnostics with
exact character ranges from the span records, so a writer sees squiggles inline.

Zero dependencies on purpose: no pygls, no lsprotocol, nothing to audit or ship
beyond the standard library, and it runs air-gapped. stdout carries the protocol;
anything else goes to stderr.

Run:  python -m articulate.lsp_server         (the editor launches it over stdio)
"""
from __future__ import annotations

import json
import sys
from urllib.parse import unquote, urlparse

from .checkext import check_text

# LSP DiagnosticSeverity: 1 Error, 2 Warning, 3 Information, 4 Hint. A writing
# tool should not raise Errors, so HIGH is a Warning, MEDIUM Information, LOW Hint.
SEVERITY = {"HIGH": 2, "MEDIUM": 3, "LOW": 4}


def _pkg_version():
    try:
        from . import __version__
        return __version__
    except Exception:  # noqa: BLE001
        return "0.0.0"


def read_message(stdin):
    """Read one Content-Length-framed JSON-RPC message, or None at EOF."""
    length = None
    while True:
        line = stdin.readline()
        if not line:
            return None
        text = line.decode("ascii", "replace").strip()
        if text == "":
            break
        if text.lower().startswith("content-length:"):
            try:
                length = int(text.split(":", 1)[1].strip())
            except ValueError:
                length = None
    if not length:
        return None
    body = stdin.read(length)
    try:
        return json.loads(body.decode("utf-8"))
    except ValueError:
        return None


def write_message(stdout, msg):
    data = json.dumps(msg, ensure_ascii=False).encode("utf-8")
    stdout.write(f"Content-Length: {len(data)}\r\n\r\n".encode("ascii"))
    stdout.write(data)
    stdout.flush()


def uri_to_path(uri):
    parsed = urlparse(uri)
    path = unquote(parsed.path or "")
    # file:///C:/x -> /C:/x ; strip the leading slash before a drive letter.
    if len(path) >= 3 and path[0] == "/" and path[2] == ":":
        path = path[1:]
    return path


def _config_for(path, config):
    """(config or None, diagnostics). A broken config is reported on line 1 and
    the document is checked without it."""
    from . import project
    try:
        return project.for_path(path, config), []
    except project.ConfigError as e:
        return None, [{"range": {"start": {"line": 0, "character": 0},
                                 "end": {"line": 0, "character": 0}},
                       "severity": 1, "code": "config", "source": "articulate",
                       "message": str(e)}]


def build_diagnostics(text, uri, override=None, config=None):
    from . import project
    path = uri_to_path(uri)
    cfg, diags = _config_for(path, config)
    prof = project.resolve(path, text, profile=override, cfg=cfg)[1]
    r = check_text(text, profile=prof)
    for f in r["high"] + r["medium"] + r["low"]:
        line0 = f["line"] - 1
        ch0 = f["col"] - 1
        ch1 = ch0 + (f["end"] - f["start"])
        diags.append({
            "range": {"start": {"line": line0, "character": ch0},
                      "end": {"line": line0, "character": ch1}},
            "severity": SEVERITY.get(f["tier"], 3),
            "code": f["rule_id"],
            "source": "articulate",
            "message": f"{f['label']}: {f['match']!r}",
        })
    return diags


def _publish(stdout, uri, diags):
    write_message(stdout, {
        "jsonrpc": "2.0",
        "method": "textDocument/publishDiagnostics",
        "params": {"uri": uri, "diagnostics": diags},
    })


def serve(stdin=None, stdout=None, profile_override=None):
    stdin = stdin if stdin is not None else sys.stdin.buffer
    stdout = stdout if stdout is not None else sys.stdout.buffer
    while True:
        msg = read_message(stdin)
        if msg is None:
            break
        method = msg.get("method")
        mid = msg.get("id")
        if method == "initialize":
            write_message(stdout, {"jsonrpc": "2.0", "id": mid, "result": {
                "capabilities": {"textDocumentSync": {"openClose": True, "change": 1}},
                "serverInfo": {"name": "articulate-lsp", "version": _pkg_version()},
            }})
        elif method == "textDocument/didOpen":
            td = msg["params"]["textDocument"]
            _publish(stdout, td["uri"],
                     build_diagnostics(td.get("text", ""), td["uri"], profile_override))
        elif method == "textDocument/didChange":
            uri = msg["params"]["textDocument"]["uri"]
            changes = msg["params"].get("contentChanges") or []
            text = changes[-1]["text"] if changes else ""
            _publish(stdout, uri, build_diagnostics(text, uri, profile_override))
        elif method == "textDocument/didClose":
            _publish(stdout, msg["params"]["textDocument"]["uri"], [])
        elif method == "shutdown":
            write_message(stdout, {"jsonrpc": "2.0", "id": mid, "result": None})
        elif method == "exit":
            break
        # other requests/notifications (initialized, etc.) need no reply


if __name__ == "__main__":
    _override = None
    if "--profile" in sys.argv:
        _i = sys.argv.index("--profile")
        if _i + 1 < len(sys.argv):
            _override = sys.argv[_i + 1]
    serve(profile_override=_override)

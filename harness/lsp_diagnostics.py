"""lsp_diagnostics.py -- diagnostics and references over the LSP bridge.

Diagnostics arrive as server-initiated notifications, so after syncing the
live buffer this module sends a cheap fence request (hover at the origin);
while the fence waits for its answer, any published diagnostics land in the
bridge's store. The returned set is honest about its bound: it is the state
as of the last fence, and a server that has not published yet yields an
empty list, never an invented one."""
from __future__ import annotations

from pathlib import Path

from .lsp_bridge import LSPError, _uri, get_bridge, lsp_query


def lsp_references(command: list, root: str, file: str, text: str,
                   language_id: str, line: int, character: int) -> dict:
    return lsp_query(command, root, file, text, language_id,
                     "references", line, character)


def lsp_diagnostics(command: list, root: str, file: str, text: str,
                    language_id: str) -> dict:
    if not isinstance(command, list) or not command:
        return {"error": "provide the language server 'command' as argv"}
    if not Path(root).is_dir():
        return {"error": f"root is not an existing directory: {root}"}
    try:
        bridge = get_bridge(command, root)
        bridge.sync_buffer(file, text, language_id)
        # The fence: while hover waits for its reply, published diagnostics
        # for the fresh buffer are read into the store.
        bridge.query("hover", file, 0, 0)
        diags = bridge.diagnostics.get(_uri(file), [])
        return {"schema": "flywheel.lsp-diagnostics/v1",
                "file": file, "n": len(diags), "diagnostics": diags,
                "note": "state as of the last request fence; an unpublished "
                        "set reads empty, never invented"}
    except LSPError as e:
        return {"error": str(e)}
    except (OSError, ValueError) as e:
        return {"error": f"{type(e).__name__}: {e}"}

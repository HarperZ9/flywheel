"""lsp_diagnostics.py -- diagnostics and references over the LSP bridge.

There are two ways a server gives out diagnostics and this route takes whichever
one the server declared. An older server pushes them as notifications, so it is
fenced: a cheap hover request cannot be answered before the notifications
already queued behind it, and by the time the fence returns anything the server
had to say has landed. A 3.17 server advertises a diagnostic provider and is
asked outright, and such a server may never push anything at all.

That second case is why this file changed. Against a real `ruff server` the
fence-only version returned a count of zero for a file with two errors in it,
and zero is exactly what a caller reads as a clean file.

What comes back is bounded in the one way that matters. `n` is null, not zero,
when the server said nothing, because a set nobody produced is unknown and a
count of it would be invented.
"""
from __future__ import annotations

from pathlib import Path

from .lsp_bridge import LSPError, _uri, get_bridge, lsp_query

#: Every reading of this route's answer, in the order they change the meaning of
#: `n`. The last clause is the one a caller acts on.
NOTE = ("diagnostics as this server hands them out ({model}); they are that "
        "server's analysis and not an independent check of the code, and a set "
        "it never produced reads unknown, never invented")


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
        published = bridge.published(file)
        known = published.version is not None or bool(published.items)
        return {"schema": "flywheel.lsp-diagnostics/v1",
                "file": file, "uri": _uri(file), "model": published.model,
                "published": known,
                "n": len(published.items) if known else None,
                "diagnostics": published.items,
                "note": NOTE.format(model=published.model)}
    except LSPError as e:
        return {"error": str(e)}
    except (OSError, ValueError) as e:
        return {"error": f"{type(e).__name__}: {e}"}

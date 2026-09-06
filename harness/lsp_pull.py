"""lsp_pull.py -- the diagnostics a client has to ask for.

LSP has two diagnostics models, and a client that speaks one of them is blind to
the servers using the other. In the older model the server pushes
`publishDiagnostics` whenever it decides it has something to say. In the 3.17
model the server advertises a `diagnosticProvider` and answers
`textDocument/diagnostic` on request, and a server built that way may never push
anything at all.

That is not a hypothetical. Against a real `ruff server` the push path sat out
its whole clock on a file with obvious problems and then reported, correctly,
that it had been told nothing. The report was honest and the client was still
useless, which is what a missing half of a protocol looks like from the outside.

Keeping the models apart, rather than flattening both into a list, is what makes
an empty set readable. A `full` report holding no items is a considered answer:
the server looked, and there was nothing. Silence on the push path is not an
answer at all. So the model that produced a set travels with the set, into the
record and onto the terminal.

One bound worth naming. A full report may carry `relatedDocuments`, diagnostics
about other files the server noticed while answering. Those are dropped here.
This asks about one document and reports on that document, and a count that
quietly included other files would not match the file the caller named.
"""
from __future__ import annotations

from .lsp_incoming import Published

#: The operation that asks. Named once so the capability check and the request
#: cannot drift apart: both go through this name.
PULL = "diagnostic"

FULL, UNCHANGED = "full", "unchanged"

__all__ = ["FULL", "PULL", "UNCHANGED", "published_from_report"]


def published_from_report(answer) -> Published:
    """One pull answer, in the shape a pushed set arrives in.

    An `unchanged` report is not an empty set. It says the diagnostics are the
    same as the ones held under a result id, and a client that never sent a
    result id holds nothing for it to be the same as. What the server said is
    "nothing new", and with no previous report that is not knowledge.

    The version here is this client's, not the server's. A pushed set carries
    the version the server was looking at; a pulled one is stamped with the
    version this side asked at, and `current` says whether the document has
    changed since. The two are different claims, which is why the model is on
    the record beside them.
    """
    report = answer.result if isinstance(answer.result, dict) else {}
    stamp = answer.stamp or {}
    uri = stamp.get("uri", "")
    if report.get("kind") != FULL:
        return Published(uri=uri, model=PULL)
    items = report.get("items")
    return Published(uri=uri,
                     items=list(items) if isinstance(items, list) else [],
                     version=stamp.get("version"), current=answer.current,
                     model=PULL)

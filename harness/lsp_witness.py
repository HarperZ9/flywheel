"""lsp_witness.py -- keep a recheckable record of what a language server said.

The chain machinery is harness/wire_witness.py, shared with the ACP witness.
What is here is the part that is about LSP: the action names that land on the
record, and the fold of one answer into the shape a receipt carries.

The fold keeps the document version and the negotiated encoding, because those
are what make an answer readable later. A range is a pair of numbers counted in
one of three encodings against one revision of a file, and a record holding the
numbers without either of those is a record of nothing. `current` is the same
fact for the reader that it is for the caller: the document did not change
between the request going out and the answer landing.

Lengths and counts, never the text. The frame chain already binds the bytes that
carried the server's answer, and a summary repeating them would put a second copy
of the file's contents in every receipt.
"""
from __future__ import annotations

from .action_witness import OUTPUT, scope as action_scope
from .wire_witness import WireWitness, transcript_resolver

FRAME_ACTION = "lsp/frame"
DECISION_ACTION = "lsp/decision"
ANSWER_ACTION = "lsp/answer"
PUBLISHED_ACTION = "lsp/published"

WITNESS_SCHEMA_V1 = "flywheel.lsp-witness/v1"
WITNESS_SCHEMA = "flywheel.lsp-witness/v2"  # v2 names `scope`

__all__ = ["ANSWER_ACTION", "DECISION_ACTION", "FRAME_ACTION", "LspWitness",
           "PUBLISHED_ACTION", "WITNESS_SCHEMA", "WITNESS_SCHEMA_V1", "scope",
           "published_summary", "summarize", "transcript_resolver"]


class LspWitness(WireWitness):
    """Binds one language server connection to one run's action chain.

    The inherited decision action is reserved rather than used. Nothing on the
    LSP path asks a policy for permission today, and naming the action here
    keeps a later policy from inventing a second vocabulary for the same record.
    """

    FRAME_ACTION = FRAME_ACTION
    DECISION_ACTION = DECISION_ACTION

    def record_answer(self, answer) -> dict:
        """Witness one folded answer beside the frames it was folded from."""
        summary = summarize(answer)
        witness = self.record(summary, action=ANSWER_ACTION, kind=OUTPUT,
                              context={"uri": summary["uri"],
                                       "operation": summary["operation"],
                                       "current": summary["current"]})
        return dict(summary, sha256=witness.sha256, link=witness.link())

    def record_published(self, published) -> dict:
        """Witness one diagnostics set, against the version it named."""
        summary = published_summary(published)
        # The model is on the context, not only in the payload, because it is
        # what tells a reader of the chain alone how to read the count under it.
        witness = self.record(summary, action=PUBLISHED_ACTION, kind=OUTPUT,
                              context={"uri": summary["uri"],
                                       "model": summary["model"],
                                       "current": summary["current"]})
        return dict(summary, sha256=witness.sha256, link=witness.link())


def summarize(answer) -> dict:
    """What one answer amounted to, in the shape a receipt carries."""
    stamp = dict(answer.stamp or {})
    document = answer.params.get("textDocument") or {}
    return {
        "schema": WITNESS_SCHEMA,
        "operation": answer.operation,
        "method": answer.method,
        "uri": stamp.get("uri") or document.get("uri", ""),
        "position": answer.params.get("position"),
        "encoding": answer.encoding,
        "version": stamp.get("version"),
        "characters": stamp.get("characters"),
        "lines": stamp.get("lines"),
        "current": answer.current,
        "results": count_of(answer.result),
        "scope": scope(),
    }


def published_summary(published) -> dict:
    """What a diagnostics set amounted to, without repeating the messages."""
    return {
        "schema": WITNESS_SCHEMA,
        "uri": published.uri,
        "model": published.model,
        "version": published.version,
        "current": published.current,
        "diagnostics": len(published.items),
        "severities": sorted({item.get("severity") for item in published.items
                              if isinstance(item, dict)
                              and item.get("severity") is not None}),
        "scope": scope(),
    }


def count_of(result: object) -> int:
    """How many things the server answered with.

    A server may answer one location, a list of them, or null, and all three are
    ordinary. Zero here means the server had nothing to say about that position,
    which is a different fact from a request that failed and is why a count sits
    on the record rather than a bare success flag.
    """
    if result is None:
        return 0
    if isinstance(result, list):
        return len(result)
    if isinstance(result, dict):
        return 1 if result else 0
    return 1


def scope() -> list[str]:
    """What an LSP run record covers. Never empty."""
    return action_scope() + [
        "the chain covers frames that crossed this connection; a server that "
        "reads files from disk can answer about text outside it",
        "an answer marked current records that the document stayed unchanged "
        "while the request was in flight; the answer itself is the server's",
        "diagnostics are the set the server chose to publish, from that "
        "server's own analysis",
        "positions are counted in the negotiated encoding; a reader converting "
        "under another encoding names a different span",
    ]

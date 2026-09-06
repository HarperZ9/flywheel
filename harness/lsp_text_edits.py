"""lsp_text_edits.py -- a list of TextEdits becomes a new string, or refuses.

The part of applying a WorkspaceEdit that never touches the filesystem. Given a
document and the edits a server returned, this produces the text those edits
describe, and raises rather than guessing when they do not describe one.

Two things go wrong here, and both are silent.

Offsets shift. Applying the second edit in an array to text the first edit
already changed moves it by the length difference, and what comes out parses and
is wrong. Every span is measured against the original document and the result is
built in one left-to-right pass, so no edit is counted against text another edit
moved.

Ranges are counted in the negotiated encoding. A `character` is utf-8 bytes,
utf-16 code units, or code points depending on what the two sides agreed at
initialize, and reading one as another cuts a file inside a character the first
time it holds an emoji.
"""
from __future__ import annotations

from .lsp_positions import DEFAULT_ENCODING, offset_of

#: Every way a WorkspaceEdit is refused, here and in lsp_edits. A caller gets
#: one of these and never a half-written document, because the whole edit is
#: checked before any file is opened to write.
REFUSALS = (
    "write-not-allowed", "not-a-file-uri", "outside-root", "no-such-file",
    "unreadable", "malformed-edit", "overlapping-edits", "stale-version",
    "needs-confirmation", "resource-operation", "write-failed",
)

__all__ = ["REFUSALS", "EditRefused", "apply_text_edits", "rebuilt",
           "spans_of"]


class EditRefused(Exception):
    """One reason a WorkspaceEdit was not applied, with what it was about."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


def _check_annotation(edit: dict, annotations: dict, confirmed) -> None:
    """Refuse an edit the server marked as needing someone to agree first.

    `needsConfirmation` is the server saying this change is not one to make
    quietly. A client that applies it anyway has answered a question that was
    put to the operator.
    """
    key = edit.get("annotationId")
    if not isinstance(key, str) or key in confirmed:
        return
    note = annotations.get(key)
    if isinstance(note, dict) and note.get("needsConfirmation"):
        label = str(note.get("label") or "")
        raise EditRefused("needs-confirmation", f"{key} {label}".strip())


def spans_of(text: str, edits: list, encoding: str = DEFAULT_ENCODING,
             annotations: dict | None = None, confirmed=()) -> list:
    """Every edit as a span of the ORIGINAL text, in the order to apply them.

    Sorted by start, ties broken by position in the array, which is the order
    the specification gives several inserts at one point. The overlap check then
    reads as one comparison: a span may begin where the last one ended and never
    before it. That admits any number of zero-width inserts at a single offset,
    which is legal, and refuses two edits claiming the same character, which is
    not.
    """
    annotations = annotations or {}
    spans = []
    for index, edit in enumerate(edits):
        if not isinstance(edit, dict):
            raise EditRefused("malformed-edit", "an edit is not an object")
        _check_annotation(edit, annotations, confirmed)
        span = edit.get("range") or {}
        start = offset_of(text, span.get("start") or {}, encoding)
        end = offset_of(text, span.get("end") or {}, encoding)
        if end < start:
            start, end = end, start
        spans.append((start, end, index, str(edit.get("newText", ""))))
    spans.sort(key=lambda item: (item[0], item[2]))
    reached = 0
    for start, end, _, _ in spans:
        if start < reached:
            raise EditRefused(
                "overlapping-edits",
                f"an edit starts at {start} inside one ending at {reached}")
        reached = end
    return [(start, end, new) for start, end, _, new in spans]


def rebuilt(text: str, spans: list) -> str:
    """The document with every span replaced, built in a single pass."""
    out: list[str] = []
    cursor = 0
    for start, end, new_text in spans:
        out.append(text[cursor:start])
        out.append(new_text)
        cursor = end
    out.append(text[cursor:])
    return "".join(out)


def apply_text_edits(text: str, edits: list,
                     encoding: str = DEFAULT_ENCODING,
                     annotations: dict | None = None, confirmed=()) -> str:
    """What a document becomes under a list of TextEdits. Nothing is written."""
    return rebuilt(text, spans_of(text, edits, encoding, annotations,
                                  confirmed))

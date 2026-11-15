"""hashline.py -- content-addressed line anchors for precise, stale-safe edits.

A `hashed` read prefixes each line with an 8-hex anchor derived from the line's
text AND its position. The model then edits by anchor instead of by repeating the
line: compact, and an anchor computed against a stale view will not match the
current file, so an edit fails closed instead of landing on the wrong line. Pure
and dependency-free, so the same anchor is derivable anywhere the ledger is read.
"""
from __future__ import annotations

import hashlib


def line_anchor(lineno: int, line: str) -> str:
    """A stable 8-hex content hash that pins one line to its position. Position is
    folded into the hash, so duplicate lines get distinct anchors and an anchor
    computed against a stale view will not match the current line."""
    return hashlib.sha256(f"{lineno}\x00{line}".encode("utf-8")).hexdigest()[:8]


def annotate_hashed(text: str) -> str:
    """The `hashed` read view: prefix each line as `<8hex>|<line>`, so the model can
    address an edit by anchor rather than by repeating the line's full text."""
    out = []
    for i, ln in enumerate(text.splitlines(keepends=True), start=1):
        out.append(f"{line_anchor(i, ln.rstrip(chr(10) + chr(13)))}|{ln}")
    return "".join(out)


def find_anchor(lines: list, anchor: str) -> int:
    """Index in `lines` (from splitlines(keepends=True)) whose anchor equals the one
    given. -1 when none match (stale or edited); -2 when two match (ambiguous)."""
    hit = -1
    for i, ln in enumerate(lines):
        if line_anchor(i + 1, ln.rstrip("\r\n")) == anchor:
            if hit != -1:
                return -2
            hit = i
    return hit


def resolve_anchor(lines: list, anchor: str) -> "tuple[int | None, str | None]":
    """(index, None) for a unique anchor; (None, error) when missing or ambiguous."""
    idx = find_anchor(lines, anchor)
    if idx == -1:
        return None, f"[error] anchor {anchor!r} not found (stale or edited since read)"
    if idx == -2:
        return None, f"[error] anchor {anchor!r} is ambiguous"
    return idx, None


def as_lines(text: str, nl: str) -> list:
    """Split replacement text into keepends lines, giving the last one `nl` when it
    has no ending of its own. Empty text yields no lines, which is a deletion."""
    if text == "":
        return []
    chunk = text.splitlines(keepends=True)
    if not chunk[-1].endswith(("\n", "\r")):
        chunk[-1] += nl
    return chunk

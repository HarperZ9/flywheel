"""udiff.py -- a strict, fail-closed unified-diff applier.

aider applies a unified diff by fuzzy-matching each hunk's context, which can land a
hunk on the wrong lines when the file has drifted. This applier refuses instead: a
hunk's pre-image (its context plus removed lines) must match the current file
EXACTLY, or the whole patch is rejected with nothing written. That is the same
fail-closed contract the hash-anchored edit tools carry, extended to a model that
speaks unified diffs. Pure line math; the executor owns IO.
"""
from __future__ import annotations

import re

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@")


def parse_hunks(diff: str) -> "tuple[list | None, str | None]":
    """Split a unified diff into hunks. Each hunk is {pre, post}: pre = context plus
    removed lines (' ' and '-'), post = context plus added lines (' ' and '+'), both
    stripped of the marker column. File headers (--- / +++) are ignored; the caller
    names the path. Returns (hunks, None) or (None, error)."""
    hunks: list = []
    cur = None
    for raw in diff.splitlines():
        if raw.startswith("--- ") or raw.startswith("+++ "):
            continue
        if _HUNK.match(raw):
            cur = {"pre": [], "post": []}
            hunks.append(cur)
            continue
        if cur is None:
            if raw.strip() == "":
                continue
            return None, "diff text appears before the first @@ hunk header"
        tag, body = raw[:1], raw[1:]
        if tag == " ":
            cur["pre"].append(body)
            cur["post"].append(body)
        elif tag == "-":
            cur["pre"].append(body)
        elif tag == "+":
            cur["post"].append(body)
        elif raw == "":                     # a bare blank line reads as blank context
            cur["pre"].append("")
            cur["post"].append("")
        else:
            return None, f"unrecognized diff line: {raw!r}"
    if not hunks:
        return None, "no @@ hunks found"
    return hunks, None


def _find_block(lines: list, block: list, start: int) -> int:
    """First index at or after `start` where `block` matches exactly, or -1. An empty
    block (a pure insertion) matches at `start`."""
    if not block:
        return start
    n = len(block)
    for i in range(start, len(lines) - n + 1):
        if lines[i:i + n] == block:
            return i
    return -1


def apply_udiff(text: str, hunks: list) -> "tuple[str | None, str | None]":
    """Apply hunks to text, fail-closed. Each hunk's pre-image must match exactly at
    or after a moving cursor, so identical blocks earlier in the file are not
    re-consumed and no fuzz is applied. Returns (new_text, None) or (None, error)."""
    lines = text.split("\n")
    out: list = []
    cursor = 0
    for h in hunks:
        i = _find_block(lines, h["pre"], cursor)
        if i == -1:
            return None, "a hunk's context did not match the file exactly (refused, no fuzz)"
        out.extend(lines[cursor:i])         # unchanged lines before the hunk
        out.extend(h["post"])               # the hunk's post-image
        cursor = i + len(h["pre"])          # consume the matched pre-image
    out.extend(lines[cursor:])
    return "\n".join(out), None

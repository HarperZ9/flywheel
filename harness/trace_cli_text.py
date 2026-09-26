"""Terminal-safe text for every trace CLI (SP-31).

Names that reach a trace command's output come from places an attacker can
shape: Claude Code project directories, `cwd` values inside transcripts, file
names in a cloned repository, store names on disk. A raw ESC sequence in one
of them can recolor the terminal, move the cursor, retitle the window or hide
the line after it. Every trace CLI prints such names through `escape`, which
shows each control character as a visible escape and never emits it.

Control characters print as `\\xHH` and bidirectional controls as `\\uHHHH`.
The mapping is injective, so two different names never print the same text.
A literal backslash is doubled only where a reader could take it for the
start of an escape: before another backslash, before `x` and two hex digits,
before `u` and four hex digits, or before a character that is itself shown
escaped. A Windows path such as `C:\\Users\\name` therefore prints as it is.
"""
from __future__ import annotations

import re
import sys

# Unicode bidirectional controls reorder the text a reader sees.
_BIDI = frozenset("\u200e\u200f\u202a\u202b\u202c\u202d\u202e"
                  "\u2066\u2067\u2068\u2069\u061c")
_LOOKS_ESCAPED = re.compile(r"\\|x[0-9a-f]{2}|u[0-9a-f]{4}")


def _shown_escaped(ch: str) -> bool:
    code = ord(ch)
    return code < 0x20 or 0x7F <= code <= 0x9F or ch in _BIDI


def _escape_char(ch: str) -> str:
    if ch in _BIDI:
        return f"\\u{ord(ch):04x}"
    if _shown_escaped(ch):
        return f"\\x{ord(ch):02x}"
    return ch


def escape(text: object) -> str:
    """Return `text` with every control and bidi character shown, not sent."""
    raw = str(text)
    out = []
    for index, ch in enumerate(raw):
        if ch != "\\":
            out.append(_escape_char(ch))
            continue
        rest = raw[index + 1:index + 6]
        ambiguous = bool(_LOOKS_ESCAPED.match(rest)) or bool(
            rest and _shown_escaped(rest[0]))
        out.append("\\\\" if ambiguous else "\\")
    return "".join(out)


def emit(line: str = "", *, stream=None) -> None:
    """Print one already-escaped line. Callers escape names, not whole lines,
    so the layout they chose (indentation, columns) survives."""
    print(line, file=stream or sys.stdout)

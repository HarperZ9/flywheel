"""lsp_positions.py -- what an LSP `character` counts, and how to get it right.

A Position in LSP is a zero-based line and a zero-based `character`, and the
unit of `character` is negotiated rather than fixed. The client offers
`general.positionEncodings` in decreasing preference, the server answers with
one in `capabilities.positionEncoding`, and both default to utf-16 when neither
says anything. utf-16 is the only kind a server must support.

This is where a client written in Python goes wrong quietly. A Python string
index counts code points, which is the utf-32 kind, and utf-32 agrees with
utf-16 on every character below U+10000. So a client that treats the two as the
same passes every ASCII test, passes accented text, passes CJK, and then reports
the wrong column for every symbol after the first emoji in the file. There is no
error when it happens. The server answers about a different span than the one
the reader is looking at.

Two more rules that are easy to miss are here for the same reason.

Line breaks are \\n, \\r\\n and \\r, and nothing else. Python's str.splitlines
also breaks on \\v, \\f, \\x1c, \\u2028 and friends, so a document holding one of
those splits into more lines here than the server sees, and every line number
after it is off by one.

A `character` that lands inside a code point rounds down to the start of that
code point, and a `character` past the end of the line clamps to the length of
the line. Both are what the specification asks for, and both keep a bad offset
from becoming an exception in the middle of a working session.
"""
from __future__ import annotations

from bisect import bisect_right
import re

UTF8 = "utf-8"
UTF16 = "utf-16"
UTF32 = "utf-32"

#: In the order a client offers them: utf-8 first because it is what a server
#: measuring bytes already has, utf-32 second because it is what Python counts,
#: utf-16 last because every server supports it and it is the fallback anyway.
ENCODINGS = (UTF8, UTF32, UTF16)

#: What both sides mean when neither names an encoding.
DEFAULT_ENCODING = UTF16

LINE_BREAK = re.compile(r"\r\n|\r|\n")


def _width_utf16(char: str) -> int:
    """Code units one code point costs in utf-16: 2 above the BMP, else 1."""
    return 2 if ord(char) > 0xFFFF else 1


def _width_utf8(char: str) -> int:
    """Bytes one code point costs in utf-8."""
    code = ord(char)
    if code < 0x80:
        return 1
    if code < 0x800:
        return 2
    if code < 0x10000:
        return 3
    return 4


_WIDTHS = {UTF8: _width_utf8, UTF16: _width_utf16}


def check_encoding(encoding: str) -> str:
    """Reject an encoding nobody negotiated, rather than guessing utf-16."""
    if encoding not in ENCODINGS:
        raise ValueError(f"position encoding is one of {ENCODINGS}, "
                         f"got {encoding!r}")
    return encoding


def character_of(line: str, index: int, encoding: str) -> int:
    """The LSP `character` for a Python index into one line of text."""
    check_encoding(encoding)
    index = max(0, min(index, len(line)))
    if encoding == UTF32:
        return index
    width = _WIDTHS[encoding]
    return sum(width(char) for char in line[:index])


def index_of(line: str, character: int, encoding: str) -> int:
    """The Python index for an LSP `character` into one line of text.

    Rounds down when the character falls inside a code point, and clamps to the
    end of the line when it falls past it.
    """
    check_encoding(encoding)
    if character <= 0:
        return 0
    if encoding == UTF32:
        return min(character, len(line))
    width = _WIDTHS[encoding]
    total = 0
    for index, char in enumerate(line):
        step = width(char)
        if total + step > character:
            return index
        total += step
    return len(line)


def split_lines(text: str) -> list[str]:
    """The document's lines, terminators removed, split the way LSP splits.

    A trailing break leaves an empty last line, because a position may sit on
    it and a server that reports one is not wrong.
    """
    return LINE_BREAK.split(text)


def line_starts(text: str) -> list[int]:
    """The Python index each line begins at. Always at least one entry."""
    starts = [0]
    starts.extend(match.end() for match in LINE_BREAK.finditer(text))
    return starts


def _line_body(text: str, starts: list[int], line: int) -> tuple[int, str]:
    """One line's start index and its text without the terminator.

    The terminator is cut because a `character` is measured against the line
    and not against the break that ends it. Leaving it in would let a position
    past the end of a line clamp onto the newline and read as column zero of
    the next one.
    """
    start = starts[line]
    end = starts[line + 1] if line + 1 < len(starts) else len(text)
    body = text[start:end]
    if body.endswith("\r\n"):
        body = body[:-2]
    elif body.endswith("\n") or body.endswith("\r"):
        body = body[:-1]
    return start, body


def offset_of(text: str, position: dict, encoding: str) -> int:
    """The Python index in `text` that an LSP Position names.

    A line past the end of the document is the end of the document, which is
    what a server means by the end position of a document-wide edit.
    """
    check_encoding(encoding)
    line = int(position.get("line", 0))
    character = int(position.get("character", 0))
    if line < 0:
        return 0
    starts = line_starts(text)
    if line >= len(starts):
        return len(text)
    start, body = _line_body(text, starts, line)
    return start + index_of(body, character, encoding)


def position_of(text: str, offset: int, encoding: str) -> dict:
    """The LSP Position for a Python index into `text`."""
    check_encoding(encoding)
    offset = max(0, min(offset, len(text)))
    starts = line_starts(text)
    line = bisect_right(starts, offset) - 1
    start, body = _line_body(text, starts, line)
    return {"line": line,
            "character": character_of(body, offset - start, encoding)}


def slice_of(text: str, span: dict, encoding: str) -> str:
    """The text an LSP Range covers, so an answer can be read against it.

    A range with its end before its start is empty rather than an error. A
    server has no reason to send one and a proxy in the middle might.
    """
    start = offset_of(text, span.get("start", {}), encoding)
    end = offset_of(text, span.get("end", {}), encoding)
    return text[start:end] if end > start else ""

"""region.py -- the byte-boundary layer of the R0 text surface.

A managed instruction file (CLAUDE.md, AGENTS.md, ...) carries at most one
canon-owned region, delimited by a column-0 begin/end marker pair:

    <!-- canon:begin scope=workspace -->
    ...canon-owned interior...
    <!-- canon:end -->

extract_region partitions the whole file into (prefix, inner, suffix) with the
byte-exact invariant `file == prefix + inner + suffix`. Everything outside the
markers is preserved to the byte; only `inner` is canon's to rewrite.
splice_region writes a new interior back and touches nothing else.

Three properties the rest of R0 leans on:

- Whole-line, column-0, CR-tolerant marker detection. We operate on file text
  read as utf-8 with newline='' (never utf-8-sig, never universal-newline
  translation), so a CRLF host keeps its `\r\n` and a leading BOM stays an
  ordinary prefix character. A marker is recognized only as a full physical
  line; a mid-line occurrence in prose is not a boundary. A byte-order mark an
  editor adds before a marker on the first line is ignored for recognition
  and kept in the prefix.

- Loud on deformation. An indented marker, a bad scope, or any illegal marker
  count (zero handled as off-limits; anything but exactly one begin + one end)
  raises RegionError rather than silently guessing or corrupting.

- Off-limits is not an error. Zero markers returns present=False with the whole
  file as prefix: a file that never opted in is simply not canon's to write.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

BEGIN_PREFIX = "<!-- canon:begin"
END_PREFIX = "<!-- canon:end"
END_MARKER = "<!-- canon:end -->"

_BEGIN_RE = re.compile(r"^<!-- canon:begin scope=(global|workspace) -->$")
_END_RE = re.compile(r"^<!-- canon:end -->$")


class RegionError(Exception):
    """The file's marker configuration is illegal or deformed: an indented or
    malformed marker, a bad scope, more than one begin/end, an end before its
    begin, or a lone begin/end. Loud by design -- never a silent off-limits."""


@dataclass(frozen=True, slots=True)
class RegionSlice:
    """A file partitioned around its canon region. Invariant at all times:
    `prefix + inner + suffix == file_text`. When present is False the file has
    no region: prefix holds the whole file and inner/suffix are empty."""

    prefix: str
    inner: str
    suffix: str
    scope: str | None
    present: bool


@dataclass(frozen=True, slots=True)
class _Marker:
    start: int      # byte offset of the line's first char
    raw_end: int    # offset just past the line's terminator (incl. \n if any)
    scope: str | None


def _iter_lines(text: str):
    """Yield (start, raw_end, body) for each physical line. `body` is the line
    content without its terminator and without a single trailing CR, so a CRLF
    line and its LF twin present the same body for marker matching. raw_end
    includes the terminator, so slicing on it preserves every byte."""
    i, n = 0, len(text)
    while i < n:
        j = text.find("\n", i)
        if j == -1:
            raw_end, content = n, text[i:n]
        else:
            raw_end, content = j + 1, text[i:j]
        body = content[:-1] if content.endswith("\r") else content
        yield i, raw_end, body
        i = raw_end


def _classify(body: str) -> str:
    """Return 'begin', 'end', or 'other' for a physical line body, raising
    RegionError on a marker-like line that is indented or malformed. Recognition
    is loose-then-validate: a column-0 line starting with the begin/end prefix is
    a marker candidate, then it must match the exact grammar or it is a loud
    error (a mistyped marker must never degrade to ordinary prose)."""
    stripped = body.lstrip(" \t")
    if stripped.startswith(BEGIN_PREFIX):
        if body != stripped:
            raise RegionError(f"indented canon:begin marker: {body!r}")
        if _BEGIN_RE.match(body) is None:
            raise RegionError(f"malformed canon:begin marker (bad scope?): {body!r}")
        return "begin"
    if stripped.startswith(END_PREFIX):
        if body != stripped:
            raise RegionError(f"indented canon:end marker: {body!r}")
        if _END_RE.match(body) is None:
            raise RegionError(f"malformed canon:end marker: {body!r}")
        return "end"
    return "other"


def extract_region(file_text: str) -> RegionSlice:
    """Partition file_text around its one canon region. Raises RegionError on any
    illegal configuration; returns present=False (whole file as prefix) when the
    file carries no marker at all."""
    begins: list[_Marker] = []
    ends: list[_Marker] = []
    for start, raw_end, body in _iter_lines(file_text):
        if start == 0 and body.startswith("\ufeff"):
            body = body[1:]  # an editor's byte-order mark stays in the prefix
        kind = _classify(body)
        if kind == "begin":
            scope = _BEGIN_RE.match(body).group(1)  # type: ignore[union-attr]
            begins.append(_Marker(start, raw_end, scope))
        elif kind == "end":
            ends.append(_Marker(start, raw_end, None))

    nb, ne = len(begins), len(ends)
    if nb == 0 and ne == 0:
        return RegionSlice(prefix=file_text, inner="", suffix="",
                           scope=None, present=False)
    if nb != 1 or ne != 1:
        raise RegionError(
            f"exactly one canon:begin and one canon:end required; "
            f"found {nb} begin, {ne} end")

    b, e = begins[0], ends[0]
    if b.start >= e.start:
        raise RegionError("canon:end marker precedes its canon:begin")
    return RegionSlice(
        prefix=file_text[:b.raw_end],
        inner=file_text[b.raw_end:e.start],
        suffix=file_text[e.start:],
        scope=b.scope,
        present=True,
    )


def splice_region(file_text: str, new_inner: str) -> str:
    """Return file_text with its region interior replaced by new_inner, every
    byte outside the markers unchanged. Raises RegionError if the file has no
    region to write (an off-limits file is never rewritten). Identity law:
    splice_region(f, extract_region(f).inner) == f."""
    s = extract_region(file_text)
    if not s.present:
        raise RegionError("no canon region to splice; file is off-limits")
    return s.prefix + new_inner + s.suffix

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
articulate.finders -- span finders for the container kinds that a plain regex
gets wrong.

A finder maps a text to a list of (start, end, key-or-None) spans, the shape
articulate.invariants expects from a container pass. The protected-span layer
and the meaning guard share these finders, so both read a span the same way.

`url_spans` applies the GitHub rule for a link's end. A URL may hold brackets,
as in https://en.wikipedia.org/wiki/Mercury_(planet), so the run takes ')' and
']' and then drops the trailing ones that close nothing inside the URL. The
closing bracket of a Markdown link and trailing punctuation stay prose, and so
does a numeric or pandoc citation written right after a URL ("docs[1]").

Each finder runs in linear time on any input. Standard library only.
"""
from __future__ import annotations

import re

TRAIL = ".,;:!?'\""
# A URL run stops at whitespace, an angle bracket, or a quote mark. It takes
# brackets; url_spans trims the unbalanced ones. The e-mail alternative keeps its
# bounded parts, which keeps it linear on a long run of dotted words.
URL_RUN = re.compile(r"\bhttps?://[^\s<>\"']+|\bwww\.[^\s<>\"']+"
                     r"|\b[\w.+-]{1,64}@[\w-]{1,63}(?:\.[\w-]{1,63}){1,8}\b")
_CITE_TAIL = re.compile(r"\[(?:\d{1,4}(?:[,–-]\d{1,4}){0,20}"
                        r"|-?@[^\[\]()\s]{1,200}|\^[\w-]{1,40})\]")
_CLOSER = {")": "(", "]": "["}


def _url_end(s, start, end):
    """The end of the URL in s[start:end] once trailing punctuation, unbalanced
    closing brackets, and a trailing citation are dropped. Each step removes at
    least one character, and the bracket counts are kept as running totals, so
    the trim is linear in the run's length."""
    opened = {c: s.count(o, start, end) for c, o in _CLOSER.items()}
    closed = {c: s.count(c, start, end) for c in _CLOSER}
    while end > start + 1:
        c = s[end - 1]
        if c in TRAIL:
            end -= 1
        elif c in _CLOSER and closed[c] > opened[c]:
            closed[c] -= 1
            end -= 1
        elif c == "]":
            i = s.rfind("[", start, end)
            if i <= start or not _CITE_TAIL.fullmatch(s, i, end):
                break
            opened[c] -= 1
            closed[c] -= 1
            end = i
        else:
            break
    return end


def url_spans(text):
    """URLs and e-mail addresses, as (start, end, None)."""
    out = []
    for m in URL_RUN.finditer(text):
        end = _url_end(text, m.start(), m.end())
        out.append((m.start(), end, None))
    return out


def _paired(text, opener, closer_of, *, min_body=1, exclusive=False, one_line=False):
    """Spans from an opener to the first closer after it, as a lazy regex such as
    '\\$\\$.+?\\$\\$' finds them, with no length cap and in linear time.

    `closer_of` maps the opener match to its closing string. A body holds at
    least `min_body` characters. An `exclusive` body cannot hold the closer, as
    in a quote. A `one_line` span ends before the next newline. When an opener
    finds no closer, no later opener with the same closer can find one either
    (before the line end, for `one_line`), so the scan skips those openers
    where the regex engine would rescan to the end from each one."""
    out, pos, n, stop = [], 0, len(text), -1
    dead = {}   # closer -> offset before which an opener with it cannot close
    while True:
        m = opener.search(text, pos)
        if m is None:
            return out
        start, closer = m.start(), closer_of(m)
        if dead.get(closer, -1) > start:
            pos = start + 1
            continue
        limit = n
        if one_line:
            if stop < start:
                stop = text.find("\n", start)
                stop = n if stop < 0 else stop
            limit = stop
        close = text.find(closer, m.end() if exclusive else m.end() + min_body, limit)
        if close < 0:
            dead[closer] = limit if one_line else n + 1
            pos = start + 1
        elif close < m.end() + min_body:
            pos = start + 1          # an exclusive body that is too short
        else:
            out.append((start, close + len(closer), None))
            pos = close + len(closer)


_QUOTE_OPEN = re.compile("[\"\u201c]")
_QUOTE_CLOSE = {"\"": "\"", "\u201c": "\u201d"}


def quote_spans(text):
    """Quoted material on one line, in straight or curly double quotes."""
    return _paired(text, _QUOTE_OPEN, lambda m: _QUOTE_CLOSE[m.group()],
                   exclusive=True, one_line=True)


def display_math_finders(envs):
    """The display-math finders in priority order: $$...$$, \\[...\\],
    \\(...\\), then each named environment from \\begin to its own \\end."""
    begin = re.compile(r"\\begin\{((?:" + "|".join(envs) + r")\*?)\}")
    fixed = [(r"\$\$", "$$"), (r"\\\[", "\\]"), (r"\\\(", "\\)")]
    finders = [lambda t, rx=re.compile(o), c=c: _paired(t, rx, lambda m, c=c: c)
               for o, c in fixed]
    finders.append(lambda t: _paired(t, begin, lambda m: "\\end{" + m.group(1) + "}",
                                     min_body=0))
    return finders

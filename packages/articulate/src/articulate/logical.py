#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""articulate.logical -- paragraphs read as logical lines.

A writer who soft-wraps a paragraph and a writer who puts one sentence per line
wrote the same text. The scanner reads both the same way: consecutive prose lines
of one paragraph join into one logical line, with a single space where each line
break was (none after a hyphen that ends a line after a letter), and an offset
map carries every match back to its file position.

What never joins: headings, table rows, table delimiter rows and horizontal rules
(each stands alone); a list item starts a new logical line that its continuation
lines join; block quote lines join only each other. Fenced code and frontmatter
are skipped. Verse (unit=line) and screenplay lines keep their physical lines,
because the line is the unit there.

Standard library only.
"""
from __future__ import annotations

import re

from .lexicon import BULLET, HEADING, WORD
from .markup import FENCE, is_md_hr, is_md_table_sep, strip_markup

_QUOTE_LEAD = re.compile(r"[ \t]*(?:>[ \t]?)+")
_LEAD = re.compile(r"[ \t]*")
# A sentence ends at . ! or ? plus any closing quote or bracket, then whitespace.
SENTENCE_END = re.compile(r"[.!?][\"'”’)\]]*\s+")


class Unit:
    """One logical line: its text and the map from text index to file offset."""
    __slots__ = ("kind", "role", "text", "pieces")

    def __init__(self, kind, role):
        self.kind, self.role, self.text, self.pieces = kind, role, "", []

    def add(self, line_no, doc_start, content):
        # A hard wrap at a hyphen ("state-of-the-" then "art") joins with no
        # space, so the word reads the same as on one line.
        if self.pieces and not (len(self.text) > 1 and self.text[-1] == "-"
                                and self.text[-2].isalpha() and content[:1].isalpha()):
            self.text += " "
        self.pieces.append((len(self.text), doc_start, line_no, len(content)))
        self.text += content

    @property
    def first_line(self):
        return self.pieces[0][2]

    def locate(self, i):
        """(file offset, line number) of text index i. A joining space maps to
        the end of the line before it."""
        for log_start, doc_start, line_no, length in reversed(self.pieces):
            if i >= log_start:
                return doc_start + min(i - log_start, length), line_no
        return self.pieces[0][1], self.pieces[0][2]

    def span(self, s, e):
        """(start, end, line, end_line) in file coordinates for text span [s, e)."""
        start, line = self.locate(s)
        last, end_line = self.locate(max(s, e - 1))
        return start, (last + 1 if e > s else start), line, end_line


def line_kinds(lines, roles=None):
    """A kind per physical line: skip, blank, hr, tablesep, heading, table, bullet,
    quote or prose. `roles` (screenplay) marks non-prose roles as skip."""
    kinds = []
    in_fence = False
    in_fm = bool(lines) and lines[0].strip() == "---"
    for i, raw in enumerate(lines):
        stripped = raw.strip()
        if FENCE.match(raw):
            in_fence = not in_fence
            kinds.append("skip")
        elif in_fence:
            kinds.append("skip")
        elif in_fm:
            if i > 0 and stripped == "---":
                in_fm = False
            kinds.append("skip")
        elif roles is not None and roles[i] not in ("action", "dialogue"):
            kinds.append("skip" if stripped else "blank")
        elif not stripped:
            kinds.append("blank")
        elif is_md_hr(raw):
            kinds.append("hr")
        elif is_md_table_sep(raw):
            kinds.append("tablesep")
        elif HEADING.match(raw):
            kinds.append("heading")
        elif stripped.startswith("|"):
            kinds.append("table")
        elif BULLET.match(raw):
            kinds.append("bullet")
        elif stripped.startswith(">"):
            kinds.append("quote")
        else:
            kinds.append("prose")
    return kinds


_ALONE = ("hr", "tablesep", "heading", "table")
_JOINS = {"prose": ("prose", "bullet", "quote"), "quote": ("quote",)}


def units(lines, *, join=True, roles=None):
    """The document's logical lines, in order."""
    kinds = line_kinds(lines, roles)
    out, cur, acc = [], None, 0
    for i, (raw, kind) in enumerate(zip(lines, kinds)):
        start, acc = acc, acc + len(raw)
        body = raw.rstrip("\r\n").rstrip()
        if kind in ("skip", "blank"):
            cur = None
            continue
        role = roles[i] if roles is not None else "prose"
        if join and cur is not None and cur.kind in _JOINS.get(kind, ()):
            lead = (_QUOTE_LEAD if kind == "quote" else _LEAD).match(body).end()
            cur.add(i + 1, start + lead, body[lead:])
            continue
        cur = Unit(kind, role)
        cur.add(i + 1, start, body)
        out.append(cur)
        if kind in _ALONE or not join:
            cur = None
    return out


# A period after one of these never ends a sentence: "Smith et al. (2019)".
# Citation abbreviations too (SCAN_ALGO 6): "(ref. 7)", "(p. 4)", "Smith v.
# Jones", "7th Cir.", "410 U.S. 113", so a citation stays in its sentence.
ABBREVIATIONS = re.compile(r"(?i)(?:\bet al|\be\.g|\bi\.e|\bcf|\bvs|\bfig|\beq|\bno|"
                           r"\bdr|\bmr|\bmrs|\bms|\bprof|\bst|\brefs?|\bpp?|\bv|\bcir|"
                           r"\bu\.s|\bvol|\bch|\bsec|\beds?)$")


def sentences(text):
    """(start, end) of each sentence in a logical line, whitespace excluded."""
    out, pos = [], 0
    for m in SENTENCE_END.finditer(text):
        if text[m.start()] == "." and ABBREVIATIONS.search(text[max(0, m.start() - 6):m.start()]):
            continue
        out.append((pos, m.start() + len(m.group(0).rstrip())))
        pos = m.end()
    if pos < len(text):
        out.append((pos, len(text)))
    return [(s, e) for s, e in out if text[s:e].strip()]


def sentence_spans(lines):
    """(line_no, sentence) for every prose sentence of three or more words, read
    over logical lines so a wrapped sentence is one sentence."""
    out = []
    for u in units(lines):
        if u.kind in ("hr", "tablesep"):
            continue
        text = strip_markup(u.text)
        for s, e in sentences(text):
            sent = text[s:e].strip()
            if len(WORD.findall(sent)) >= 3:
                out.append((u.locate(s)[1], sent))
    return out

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""articulate.desk_inside -- the "Inside the document" half of the desk.

Deterministic checks of the document's own statements, each turned into one
question for a reviewer: a number with no source nearby, an appeal to unnamed
authority, a section or statement the venue asks for and cannot find, text that
does not show to a reader, and the one criteria question a venue may set for
every submission alike. No question asks how a text came about. Quotations and code are skipped.

It loads two rule families and no others: the unsupported-authority pattern
and the instruction-injection patterns (used only to say whether hidden text
is addressed to a model). No style rule, no density and no per-paragraph gate.
Standard library only.
"""
from __future__ import annotations

import re

from .citations import unanchored_appeals
from .detector import detect_injection, segment_blocks
from .logical import sentences, units

VENUES = {
    "none": {},
    "paper": {"sections": ("limitations",), "tool_statement": True},
    "course": {"tool_statement": True,
               "criteria_question": "Which assignment criterion does each section serve?"},
}
HIDDEN_QUESTION = "This passage does not show to a reader. Should it be in the submission?"

_NUMBER = re.compile(r"(?<![\w.])\d+(?:\.\d+)?%|(?<![\w.,])\d{1,3}(?:,\d{3})+(?![\d,])"
                     r"|(?<![\w.])\d+\.\d+(?![\d.])")
_CITED = re.compile(r"\[\d+(?:[,–-]\s*\d+)*\]|\([^()]*\b(?:1[89]|20)\d\d[a-z]?\)|et al\."
                    r"|https?://|\bdoi:|\b(?:Table|Figure|Fig\.|Section|Appendix)\s+\d")
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_OWN_TAGS = re.compile(r"(?i)writing-(?:profile|allow):|BEGIN C2PA MANIFEST")
# Characters that do not render: zero-width joiners and spaces between Latin
# letters (ZWNJ and ZWJ are ordinary inside Arabic, Persian, Indic and emoji
# sequences, so only a Latin run counts), a byte-order mark after the first
# character, bidirectional controls, and Unicode tag characters (U+E0000 block),
# which can carry a whole hidden sentence.
_INVISIBLE = re.compile(
    "(?<=[A-Za-z0-9])[\u200b\u200c\u200d\u2060]+(?=[A-Za-z0-9])"
    "|(?<=.)\ufeff|[\u202a-\u202e\u2066-\u2069]+|[\U000e0000-\U000e007f]+", re.S)
# Styling that hides text. Each value must hide it: white text, a zero size,
# display none, visibility hidden, zero opacity. `background-color` and a size
# such as 0.9em are ordinary styling and never match.
_HIDE = (r"(?:(?<![-\w])color\s*:\s*(?:#fff(?:fff)?(?![\w])|white\b)"
         r"|font-size\s*:\s*0(?:px|em|rem|pt|%)?(?![\w.])"
         r"|display\s*:\s*none\b|visibility\s*:\s*hidden\b"
         r"|opacity\s*:\s*0(?:\.0+)?(?![\w.]))")
_STYLED = re.compile(r"(?i)<[^>]+style\s*=\s*(?:\"[^\"]*" + _HIDE + r"[^\"]*\""
                     r"|'[^']*" + _HIDE + r"[^']*')[^>]*>[^<]*"
                     r"|\\textcolor\{white\}\{[^}]*\}|\\color\{white\}[^\n}]*")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$|\\(?:sub)*section\*?\{([^}]*)\}", re.M)


def _item(check, line, quote, question, **extra):
    return {"check": check, "line": line, "quote": quote.strip()[:240],
            "question": question, **extra}


def _paragraph_of(blocks, line):
    for i, b in enumerate(blocks, 1):
        if b["start_line"] <= line <= b["end_line"]:
            return i
    return len(blocks)


def claim_items(text):
    """Numbers with no source nearby and appeals to unnamed authority."""
    from .desk_field import without_comments
    blocks = segment_blocks(text)
    out = []
    for u in units(without_comments(text).splitlines(keepends=True)):
        if u.kind in ("quote", "hr", "tablesep"):
            continue
        for s, e in sentences(u.text):
            sent, line = u.text[s:e], u.locate(s)[1]
            if not _CITED.search(sent):
                for m in _NUMBER.finditer(sent):
                    out.append(_item("number-without-source", line, sent,
                                     f"Where does {m.group(0)} in paragraph "
                                     f"{_paragraph_of(blocks, line)} come from?"))
            for a, b in unanchored_appeals(sent, sent):
                out.append(_item("unsupported-authority", line, sent,
                                 f"Which sources does '{sent[a:b]}' refer to?",
                                 category="unsupported-authority"))
    return out


def _outside_quotes_and_code(text):
    """The text with fenced code and block-quote lines blanked, offsets kept."""
    lines, fence = text.splitlines(keepends=True), False
    out = []
    for ln in lines:
        marker = ln.lstrip().startswith(("```", "~~~"))
        if marker:
            fence = not fence
        if marker or fence or ln.lstrip().startswith(">"):
            out.append("".join(c if c == "\n" else " " for c in ln))
        else:
            out.append(ln)
    return "".join(out)


def _untag(span):
    """Tag characters mirror ASCII (U+E0020 is a space, U+E0041 is 'A'), so the
    hidden sentence they carry can be read for the injection check."""
    return "".join(chr(ord(c) - 0xE0000) if 0xE0020 <= ord(c) <= 0xE007E else c
                   for c in span)


def _shown(span):
    """The span with each invisible character written as its code point, and a
    run of tag characters written as the text it spells."""
    out, tags = [], []
    for c in span + " ":
        if 0xE0000 <= ord(c) <= 0xE007F:
            tags.append(c)
            continue
        if tags:
            out.append(f"[tag characters spelling: {_untag(''.join(tags))}]")
            tags = []
        out.append(f"[U+{ord(c):04X}]" if _INVISIBLE.fullmatch(c) or c in _MARKS else c)
    return "".join(out)[:-1]


_MARKS = "\u200b\u200c\u200d\u2060\ufeff"


def hidden_items(text):
    """Text that does not render for a reader, outside quotations and code."""
    visible = _outside_quotes_and_code(text)
    out = []
    for rx in (_COMMENT, _INVISIBLE, _STYLED):
        for m in rx.finditer(visible):
            span = text[m.start():m.end()]
            if rx is _COMMENT and _OWN_TAGS.search(span):
                continue
            line = text.count("\n", 0, m.start()) + 1
            out.append(_item("hidden-text", line, _shown(span), HIDDEN_QUESTION,
                             addressed_to_model=bool(detect_injection(_untag(span)))))
    return out


def venue_items(text, venue, disclosure):
    rules = VENUES.get(venue or "none")
    if rules is None:
        raise ValueError(f"unknown venue {venue!r}; known: {sorted(VENUES)}")
    heads = " ".join((a or b).lower() for a, b in _HEADING.findall(text))
    out = []
    for sec in rules.get("sections", ()):
        if sec not in heads:
            out.append(_item("missing-section", 0, "",
                             f"The venue asks for a {sec} section. Where are the "
                             f"{'limits' if sec == 'limitations' else sec} stated?"))
    if rules.get("tool_statement") and not (disclosure or "").strip():
        out.append(_item("missing-tool-statement", 0, "",
                         "The venue asks for a statement of tool use. Is one attached?"))
    if rules.get("criteria_question"):
        out.append(_item("criteria-question", 0, "", rules["criteria_question"]))
    return out


def author_items(field_claims):
    """Author side: presence checks with spans, asked before submission."""
    asks = (("states-contribution", ("learn", "change"),
             "Where does the draft state what it contributes, in a sentence a reviewer can quote?"),
            ("names-prior-work", ("prior",),
             "Which closest prior work does the draft build on, and where does it name it?"),
            ("states-what-it-enables", ("future",),
             "Where does the draft say what future work it makes possible?"))
    return [_item(check, 0, "", q) for check, ids, q in asks
            if not any(field_claims.get(i) for i in ids)]

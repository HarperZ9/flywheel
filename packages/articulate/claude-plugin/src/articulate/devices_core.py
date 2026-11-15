"""Shared helpers for the device readers: sentences, clauses, members, hits.

Standard library only.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from . import devices_lex as X

_SENT = re.compile(r"[^.!?]+[.!?]*")
_CLAUSE = re.compile(r"[^,;:]+")
_SPLIT_BUT = re.compile(r"\s+(?=\b(?:but|yet)\b)", re.I)
_NEG = re.compile(r"\b(?:not|never|no)\b|n't\b", re.I)


def sentences(text):
    """(start, sentence) for each sentence, blank-line paragraphs kept apart."""
    out = []
    text = text.replace("’", "'")
    for block in _BLOCK.finditer(text):
        if block.group(0).lstrip()[:1] in ("#", "|"):
            continue                      # headings and table rows are not prose
        for m in _SENT.finditer(block.group(0)):
            s = m.group(0)
            if X.words(s):
                out.append((block.start() + m.start() + len(s) - len(s.lstrip()), s.strip()))
    return out


# A block ends at a blank line, and a heading, list item, table row or quote
# line stands alone, so a heading never runs into the sentence below it.
_MARK = r"[ \t]*(?:#|[-*+] |\d+\. |\||>)"
_BLOCK = re.compile(r"(?m)^" + _MARK + r".*$|(?:^(?!" + _MARK + r")(?![ \t]*$).*(?:\n|$))+")


def clauses(sentence, split_but=False):
    parts = [c.strip() for c in _CLAUSE.findall(sentence) if X.words(c)]
    if split_but:
        parts = [q.strip() for c in parts for q in _SPLIT_BUT.split(c) if X.words(q)]
    return parts


def _strip_lead(ws):
    while ws and X.norm(ws[0]) in X.COORD:
        ws = ws[1:]
    return ws


def _sim(a, b):
    return SequenceMatcher(None, X.classes(a), X.classes(b), autojunk=False).ratio()


def _parallel(a, b):
    """Two members read as parallel: same opener, or a matching skeleton."""
    a, b = _strip_lead(a), _strip_lead(b)
    if not a or not b:
        return False
    if X.norm(a[0]) == X.norm(b[0]) and (len(a) > 1 or len(b) > 1 or a[0].lower() == b[0].lower()):
        return True
    return abs(len(a) - len(b)) <= 2 and _sim(a, b) >= 0.6


def _hit(device, start, snippet, detail=""):
    return {"device": device, "start": start, "snippet": snippet[:100], "detail": detail}


def _pairs(sents, split_but=False):
    """Adjacent clause pairs inside each sentence, then adjacent short sentences."""
    for start, s in sents:
        cs = clauses(s, split_but)
        for a, b in zip(cs, cs[1:]):
            yield start, s, X.words(a), X.words(b), a + " | " + b
    for (start, a), (_, b) in zip(sents, sents[1:]):
        wa, wb = X.words(a), X.words(b)
        if len(wa) <= 12 and len(wb) <= 12:
            yield start, a + " " + b, wa, wb, a + " | " + b


def _dedupe(hits):
    seen, out = set(), []
    for h in hits:
        if (h["device"], h["start"]) not in seen:
            seen.add((h["device"], h["start"]))
            out.append(h)
    return out

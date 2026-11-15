"""Analogy, read for the structure it carries across.

An analogy maps one domain onto another the reader already knows. A good one
carries structure: two or more corresponding parts ("the reviewer is the
co-pilot, the diff is the checklist") or a relation that holds on both sides
("a key is to a lock as a token is to a server", "just as ..., so ..."). A
stock comparison ("like a rollercoaster") carries no structure at all.

`find(text)` returns analogy hits in the shape of articulate.devices findings,
each with its own verdict:

  carries   two or more mapped parts, or a relation carried across
  empty     a bare comparison with a stock vehicle, or an analogy frame with
            nothing mapped inside it

Frames read: "is to ... as", "just as ... so", "think of ... as", "picture ...
as", "in the same way as", "the way ... is the way", "works like" or "is like"
followed by a colon or a mapping clause, and "like a" with a stock vehicle. A
comparison inside one domain with real figures ("build 2 runs in 2.1 seconds,
like build 1") has no vehicle from another domain and is not read as a device.

`points_at_map(text)` says whether a passage points at a testable map: what
corresponds to what, where the map breaks, a prediction through it, or a
link. Research writing uses it as advice: an analogy that carries an argument
should become a map that can fail. Standard library only.
"""
from __future__ import annotations

import re

from . import devices_lex as X
from . import imagery_lex as L
from .devices_core import sentences

STOCK_COMPARISON = frozenset("""
rollercoaster roller-coaster rocket charm dream breeze machine clockwork bull kid
candy shop storm hurricane wildfire whirlwind magic
""".split())

_FRAME = re.compile(
    r"(?i)\b(?:is to\b.{1,80}?\bas\b|just as\b|think of\b.{1,60}?\bas\b|picture\b.{1,60}?\bas\b|"
    r"in the same way (?:as|that)\b|the way\b.{1,80}?\bis the way\b|"
    r"(?:works?|acts?|behaves?|is|are|was|were) (?:a lot |much )?like (?:a|an|the)\b)")
_PAIR = re.compile(
    r"(?i)\b(?:the|a|an|your|my|our|their|its|his|her) [\w'’-]+ (?:is|are|becomes|plays|"
    r"acts as|stands in for) (?:the|a|an|your|my|our|their|its) [\w'’-]+")
_RELATION = re.compile(r"(?i)\bis to\b.{1,80}?\bas\b|\bjust as\b.{1,160}?\bso\b|\bin the same way (?:as|that)\b"
                       r"|\bthe way\b.{1,80}?\bis the way\b")
_DIGIT = re.compile(r"\d")
_BARE = re.compile(r"(?i)\blike an?$|\bthink of\b|\bpicture\b")
_LIKE_STOCK = re.compile(r"(?i)\blike (?:a|an|the) ([\w'’-]+)")
_MAP = re.compile(
    r"(?i)\bmaps? (?:onto|to)\b|\bcorrespond(?:s|ing)? to\b|\bpredicts?\b|\bbreaks? (?:down )?"
    r"(?:when|where|if)\b|\bfails? (?:when|where|if)\b|\bholds? (?:until|only|when|while)\b|"
    r"\brange of validity\b|\bhomolog\w*\b|\btestable\b|\bfalsif\w*\b|https?://|\]\(")


def _window(sents, i, n=2):
    return " ".join(s for _st, s in sents[i:i + n])


def _structure(window):
    pairs = len(_PAIR.findall(window))
    relation = bool(_RELATION.search(window))
    return pairs, relation


def find(text):
    """Analogy hits with their verdict and the structure behind it."""
    sents = sentences(text)
    hits = []
    for i, (start, s) in enumerate(sents):
        frame = _FRAME.search(s)
        stock = next((m for m in _LIKE_STOCK.finditer(s)
                      if m.group(1).lower() in STOCK_COMPARISON | L.STOCK), None)
        if not frame and not stock:
            continue
        window = _window(sents, i, 2 if s.rstrip().endswith(":") or frame else 1)
        pairs, relation = _structure(window)
        if frame and not stock and not (pairs or relation) and not L.image_words(X.words(s)):
            # A literal comparison inside one domain: real figures, or "like the old one".
            if _DIGIT.search(s) or not _BARE.search(frame.group(0)):
                continue
        carries = pairs >= 2 or relation
        loads = (["structure"] if carries else []) + (["stance"] if L.STANCE.search(window) else [])
        detail = (f"{pairs} mapped parts" if pairs >= 2 else "relation carried across"
                  if relation else f"stock comparison: {stock.group(1)}" if stock
                  else "no mapped parts")
        hits.append({"device": "analogy", "start": start + (frame or stock).start(),
                     "snippet": s[:100], "detail": detail,
                     "verdict": "carries" if carries else "empty", "carries": loads,
                     "stock": [stock.group(1).lower()] if stock and not carries else [],
                     "map": points_at_map(window)})
    return hits


def points_at_map(text):
    """True when the passage names a correspondence, a break point, a prediction or a link."""
    return bool(_MAP.search(text or ""))

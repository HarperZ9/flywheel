"""Rhetorical devices read from structure: thirteen readers, one finding shape.

The line checker (detector.py) is byte-pinned and reads a few devices through
narrow patterns: antithesis only with a negation, the triad only as single words
with a serial comma, anaphora only as sentence runs with a content-word opener.
This module reads devices more completely, as a separate report:

  antithesis    opposed words across balanced clauses, or a negated clause
                answered by a parallel affirmative one (in one sentence or two)
  tricolon      three parallel members of up to six words, any joiner, with or
                without a serial comma
  anaphora      three or more sentences, or clauses inside a sentence, that
                open with the same word (two words when the first is an article)
  chiasmus      content words in A B ... B A order across a clause boundary
  polysyndeton  one conjunction repeated before three or more short members
  asyndeton     three or more parallel members with no conjunction
  anadiplosis   a clause ending on the word that opens the next
  epizeuxis     a word repeated at once ("never, never")
  isocolon      adjacent clauses of near-equal length and parallel structure
  zeugma        one head taking a concrete object and an abstract one
  oxymoron      opposed words side by side
  alliteration, assonance   see devices_sound

A device is a shape writers of every kind use, on purpose and by habit. A
finding names where the shape is; it says nothing about who wrote the text, and
none of these readers gates a check. Standard library only.
"""
from __future__ import annotations

import re

from . import devices_lex as X
from . import devices_series as S
from . import devices_sound
from .devices_core import _NEG, _dedupe, _hit, _pairs, _sim, _strip_lead, sentences

DEVICES = ("antithesis", "tricolon", "anaphora", "chiasmus", "alliteration", "assonance",
           "polysyndeton", "asyndeton", "anadiplosis", "epizeuxis", "isocolon", "zeugma",
           "oxymoron")


def _elliptic(ws):
    """A member that opens without its own subject ('but marks where ...')."""
    return bool(ws) and X.norm(ws[0]) not in X.PRONOUN_SUBJ | X.ARTICLES


def antithesis(sents):
    out, seen = [], set()
    for start, s, a0, b0, snip in _pairs(sents, split_but=True):
        a, b = _strip_lead(a0), _strip_lead(b0)
        if not a or not b or len(a) > 12 or len(b) > 12 or (start, snip) in seen:
            continue
        opp = next(((x, y) for x in a for y in b if X.opposed(x, y)), None)
        balanced = abs(len(a) - len(b)) <= 3 or _sim(a, b) >= 0.5
        neg_a = bool(_NEG.search(" ".join(a)))
        neg_b = bool(_NEG.search(" ".join(b)))
        detail = None
        if opp and balanced:
            detail = f"{opp[0]} / {opp[1]}"
        elif neg_a != neg_b:
            pa = [w for w in a if not _NEG.fullmatch(w)]
            pb = [w for w in b if not _NEG.fullmatch(w)]
            if _sim(pa, pb) >= 0.65 and [X.lemma(w) for w in X.content(pa)] != \
                    [X.lemma(w) for w in X.content(pb)]:
                detail = "negated member and its answer"
            elif neg_a and b0 and X.norm(b0[0]) in ("but", "yet") and _elliptic(b):
                detail = "not X but Y"
        if detail:
            seen.add((start, snip))
            out.append(_hit("antithesis", start, snip, detail))
    return out


_SMALL = X.ARTICLES | X.COORD | X.PRONOUN_SUBJ | frozenset(
    "is am are was were be been has have had of to in on at by with from not no what who "
    "which that me him her us them my your his its our their over under into onto upon about "
    "after before through up down out off very just also more most much many".split())


def chiasmus(sents):
    out = []
    for start, s in sents:
        toks = [(m.start(), X.lemma(m.group(0))) for m in X.WORD.finditer(s)
                if X.norm(m.group(0)) not in _SMALL]
        bounds = [m.start() for m in re.finditer(r"[,;:]|\b(?:and|but|or)\b", s)]
        lems = [lm for _, lm in toks]
        found = None
        for i in range(len(toks)):
            for l in range(len(toks) - 1, i + 2, -1):
                if toks[l][1] != toks[i][1] or toks[l][0] - toks[i][0] > 80:
                    continue
                for j in range(i + 1, l - 1):
                    for k in range(j + 1, l):
                        if toks[j][1] == toks[k][1] != toks[i][1] and \
                                lems.count(toks[i][1]) == 2 and lems.count(toks[j][1]) == 2 and \
                                any(toks[j][0] < b < toks[k][0] for b in bounds):
                            found = (toks[i][1], toks[j][1])
                            break
                    if found:
                        break
                if found:
                    break
            if found:
                break
        if found:
            out.append(_hit("chiasmus", start, s, f"{found[0]} {found[1]} / {found[1]} {found[0]}"))
    return out


def _head(ws):
    while ws and X.norm(ws[0]) in ("and", "or", "nor", "but", "yet", "so", "then"):
        ws = ws[1:]
    while ws and X.norm(ws[0]) in X.ARTICLES:
        ws = ws[1:]
    return ws[0] if ws else None


def anadiplosis(sents):
    out, units = [], []
    for start, s in sents:
        units += [(start, X.words(c)) for c in re.split(r"[,;:]", s) if X.words(c)]
    for (start, a), (_, b) in zip(units, units[1:]):
        ca, head = X.content(a), _head(b)
        if len(a) >= 2 and ca and head and X.norm(a[-1]) == X.norm(ca[-1]) \
                and X.norm(head) not in X.FUNCTION and X.same_word(ca[-1], head):
            out.append(_hit("anadiplosis", start, " ".join(a[-3:] + ["|"] + b[:3]), ca[-1]))
    return _dedupe(out)


_PREP = re.compile(r"(?i)^(?:of|by|for|in|on|at|from|with|under|over|after|before)$")


def isocolon(sents):
    out = []
    for start, s, a0, b0, snip in _pairs(sents):
        a, b = _strip_lead(a0), _strip_lead(b0)
        if 2 <= len(a) <= 10 and 2 <= len(b) <= 10 and abs(len(a0) - len(b0)) <= 1 \
                and _sim(a, b) >= 0.7 and not (_PREP.match(a[0]) or _PREP.match(b[0])):
            out.append(_hit("isocolon", start, snip, f"{len(a)} and {len(b)} words"))
    return _dedupe(out)


_AND_PAIR = re.compile(r"((?:[A-Za-z'-]+\s+){1,4}?)and\s+((?:[A-Za-z'-]+\s*){1,3})")


def zeugma(sents):
    out = []
    for start, s in sents:
        for m in _AND_PAIR.finditer(s):
            left = [X.norm(w) for w in X.words(m.group(1))]
            right = [X.norm(w) for w in X.words(m.group(2))]
            kinds_l = {"c" for w in left if w in X.CONCRETE} | {"a" for w in left if w in X.ABSTRACT}
            kinds_r = {"c" for w in right if w in X.CONCRETE} | {"a" for w in right if w in X.ABSTRACT}
            if len(kinds_l) == 1 and len(kinds_r) == 1 and kinds_l != kinds_r:
                out.append(_hit("zeugma", start, m.group(0).strip()))
                break
    return out


_BREAK = frozenset({"and", "or", "nor", "but", "to", "from", "than", "versus", "vs", "kind", "sort",
                    "is", "are", "was", "were", "be", "been"})


def oxymoron(sents):
    out = []
    for start, s in sents:
        for seg in re.split(r"[,;:.!?]", s):
            ws = X.words(seg)
            hit = None
            for i, w in enumerate(ws):
                for j in range(i + 1, min(len(ws), i + 4)):
                    if any(X.norm(x) in _BREAK for x in ws[i + 1:j + 1]):
                        break
                    if X.opposed(w, ws[j]):
                        hit = (w, ws[j])
                        break
                if hit:
                    break
            if hit:
                out.append(_hit("oxymoron", start, seg.strip(), f"{hit[0]} / {hit[1]}"))
    return out


def analyze(text):
    """Every device finding in text, with counts by device."""
    sents = sentences(text)
    hits = (antithesis(sents) + S.series(sents) + S.anaphora(sents) + chiasmus(sents)
            + S.polysyndeton(sents) + anadiplosis(sents) + S.epizeuxis(sents) + isocolon(sents)
            + zeugma(sents) + oxymoron(sents) + devices_sound.alliteration(sents)
            + devices_sound.assonance(sents))
    hits.sort(key=lambda h: (h["start"], h["device"]))
    counts = {d: 0 for d in DEVICES}
    for h in hits:
        counts[h["device"]] += 1
    return {"findings": hits, "counts": counts}

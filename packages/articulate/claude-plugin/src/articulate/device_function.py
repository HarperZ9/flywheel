"""Literary devices, named, with a reading of the work each one does.

A device is a tool. Antithesis, anaphora, tricolon, chiasmus, metaphor, simile
and motif all carry meaning in good writing, and the same shapes turn up as
filler in machine-default prose. The shape alone cannot tell the two apart;
the words inside it can. This module names every device it finds and reads
the sentence that holds it for three kinds of load:

  image    a word a reader can picture: a thing, a place, weather, a body, a
           sense verb (articulate.imagery_lex)
  anchor   a number, a date, a quotation, inline code, a link, a name, or a
           concrete technical thing (a file, a log, a test)
  stance   an argument joint (because, unless, which means) or a first-person
           verb that takes a position (I think, I saw, I doubt)

A device whose sentence carries none of these, or whose figure rests on a stock
vehicle (journey, tapestry, landscape, beacon) with no image or anchor beside
it, reads as `empty`. Every other device reads as `carries`, with the loads
listed. The verdict is a reading for the author to judge, never an edit.

Readers: the thirteen structural readers in articulate.devices, plus simile,
metaphor and motif here, and analogy (articulate.analogy), which carries its
own verdict: `carries` when it maps two or more parts or a relation across,
`empty` when it is a bare stock comparison. Motif is an image noun that returns in three or more
paragraphs. Rhythm is reported as the spread of sentence lengths. Irony and
synecdoche depend on context these surface readers cannot see, so this module
names them as unread. Standard library only.
"""
from __future__ import annotations

import re

from . import analogy, devices
from . import devices_lex as X
from . import imagery_lex as L
from . import voice_features as vf
from .devices_core import sentences

FIGURES = ("simile", "metaphor", "motif", "analogy")
UNREAD = ("irony", "synecdoche")
# The figures the empty reading is applied to in a check; the rest are named only.
JUDGED = frozenset({"antithesis", "tricolon", "anaphora", "asyndeton", "chiasmus", "epizeuxis",
                    "metaphor", "simile", "analogy"})
SCOPE = ("Names device shapes and reads the words inside them for an image, an anchor "
         "or a stance. The author decides whether each device earns its place.")

_SIMILE = re.compile(r"(?i)(?<![Ii] )(?<!we )(?<!you )(?<!they )(?<!'d )(?<!would )"
                     r"\b(?:like|as if|as though)\s+((?:[a-z'’-]+\s+){0,4}[a-z'’-]+)")
_METAPHOR = re.compile(r"(?i)\b([a-z'’-]+)\s+(?:is|are|was|were|becomes|became)\s+"
                       r"(?:a|an|the|our|my|your|its|their)\s+((?:[a-z'’-]+\s+){0,2}[a-z'’-]+)")
_PARA = re.compile(r"\n\s*\n")


def judge(sentence):
    """{'verdict', 'carries', 'stock'} for the sentence that holds a device."""
    ws = X.words(sentence)
    loads = []
    if L.image_words(ws):
        loads.append("image")
    if L.ANCHOR.search(sentence) or L.thing_words(ws):
        loads.append("anchor")
    if L.STANCE.search(sentence):
        loads.append("stance")
    stock = sorted({w.lower() for w in ws if w.lower() in L.STOCK}
                   | {m.group(0).lower() for m in L.STOCK_PHRASES.finditer(sentence)})
    if stock and not ({"image", "anchor"} & set(loads)):
        return {"verdict": "empty", "carries": loads, "stock": stock}
    return {"verdict": "carries" if loads else "empty", "carries": loads, "stock": stock}


def _holding(sents, start, length):
    """The text of the sentences from the one holding start, enough to cover length."""
    out, got = [], 0
    for s_start, s in sents:
        if s_start + len(s) <= start and not out:
            continue
        out.append(s)
        got += len(s) + 1
        if got >= length:
            break
    return " ".join(out)


def _vehicle(words):
    for w in X.words(words):
        low = w.lower()
        if low in L.STOCK or L.image_words([w]):
            return low
    return None


def figures(text):
    """Simile, metaphor and motif hits, in the shape of articulate.devices findings."""
    hits = []
    for start, s in sentences(text):
        for m in _SIMILE.finditer(s):
            v = _vehicle(m.group(1))
            if v:
                hits.append({"device": "simile", "start": start + m.start(),
                             "snippet": s[:100], "detail": v})
        for m in _METAPHOR.finditer(s):
            tenor, v = m.group(1).lower(), _vehicle(m.group(2))
            if v and not L.image_words([tenor]) and tenor not in X.PRONOUN_SUBJ:
                hits.append({"device": "metaphor", "start": start + m.start(),
                             "snippet": s[:100], "detail": f"{tenor} / {v}"})
    hits.extend(_motifs(text))
    return hits


def _motifs(text, minimum=3):
    seen = {}
    pos = 0
    for para in _PARA.split(text):
        at = text.find(para, pos)
        pos = at + len(para)
        for w in set(L.image_words(X.words(para))):
            seen.setdefault(w, []).append(at)
    return [{"device": "motif", "start": starts[0], "snippet": w,
             "detail": f"returns in {len(starts)} paragraphs"}
            for w, starts in sorted(seen.items()) if len(starts) >= minimum]


def _line(text, offset):
    return text.count("\n", 0, offset) + 1


def analyze(text):
    """Every device with its line, its verdict and the loads it carries."""
    sents = sentences(text)
    analogies = analogy.find(text)
    covered = {_line(text, a["start"]) for a in analogies}
    found = devices.analyze(text)["findings"] + [
        f for f in figures(text)
        if not (f["device"] == "simile" and _line(text, f["start"]) in covered)]
    rows = [dict(a, line=_line(text, a["start"])) for a in analogies]
    for f in sorted(found, key=lambda h: (h["start"], h["device"])):
        if f["device"] == "motif":
            verdict = {"verdict": "carries", "carries": ["image"], "stock": []}
        else:
            verdict = judge(_holding(sents, f["start"], len(f["snippet"])))
        rows.append(dict(f, line=_line(text, f["start"]), **verdict))
    rows.sort(key=lambda r: (r["start"], r["device"]))
    names = devices.DEVICES + FIGURES
    counts = {d: sum(1 for r in rows if r["device"] == d) for d in names}
    cv = vf.scalars(vf.measure(text))["sentence_len_cv"] if text.strip() else None
    return {"devices": rows, "counts": counts,
            "carrying": sum(1 for r in rows if r["verdict"] == "carries"),
            "empty": sum(1 for r in rows if r["verdict"] == "empty"),
            "rhythm": {"sentence_len_cv": cv}, "unread": list(UNREAD), "scope": SCOPE}

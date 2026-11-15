"""Series devices: tricolon, asyndeton, anaphora, polysyndeton, epizeuxis.

A series is a run of parallel members split on commas and semicolons, with a
final "X and Y" split in two. Parallel means the same opener, or a matching
coarse word-class skeleton (devices_lex.classes). Standard library only.
"""
from __future__ import annotations

import re

from . import devices_lex as X
from .devices_core import _dedupe, _hit, _parallel, _strip_lead, clauses

def _members(sentence):
    """Comma and semicolon members; the last one splits on 'and'/'or' into two."""
    cs = [c for c in re.split(r"[,;:]", sentence) if X.words(c)]
    out = []
    for i, c in enumerate(cs):
        m = re.match(r"(.*?)\b(and|or|nor)\b\s+(.*)$", c.strip(), re.I)
        if m and i == len(cs) - 1 and i > 0 and X.words(m.group(1)) and X.words(m.group(3)):
            out.append((X.words(m.group(1)), False))
            out.append((X.words(m.group(3)), True))
        else:
            out.append((X.words(c), bool(re.match(r"\s*(?:and|or|nor)\b", c, re.I))))
    return out


def _runs(sentence):
    """Maximal runs of parallel series members, each with a flag saying whether a
    parallel member sits just past the run (so the series is longer than shown)."""
    ms = _members(sentence)
    runs, i = [], 0
    while i < len(ms) - 1:
        j = i + 1
        while j < len(ms) and len(ms[j][0]) <= 6 + (3 if ms[j][1] else 0) \
                and _member_parallel(ms[j - 1][0], ms[j][0], ms[j][1], j - 1 == i):
            j += 1
        if j - i >= 3:
            longer = j < len(ms) and _parallel(ms[j - 1][0], ms[j][0])
            runs.append((ms[i:j], longer))
            i = j - 1
        else:
            i += 1
    return runs


def _member_parallel(prev, cur, conj_led, prev_is_first):
    cur = _strip_lead(cur)
    if prev_is_first and len(prev) > len(cur):
        prev = prev[len(prev) - max(1, len(cur)):]
    if conj_led and len(cur) <= len(prev) + 3 and len(prev) <= 6:
        return True
    return len(prev) <= 6 and _parallel(prev, cur)


def _names_only(run):
    """A list of proper names (Boston, Salem and Newport) is a list, not a figure."""
    return all(_strip_lead(m)[:1] and _strip_lead(m)[0][:1].isupper()
               and X.norm(_strip_lead(m)[0]) not in X.FUNCTION for m, _ in run[1:])


def series(sents):
    """tricolon and asyndeton findings from the parallel member runs."""
    out = []
    for start, s in sents:
        for run, longer in _runs(s):
            if _names_only(run):
                continue
            joined = " | ".join(" ".join(m) for m, _ in run)
            if len(run) == 3 and not longer:
                out.append(_hit("tricolon", start, joined))
            if not any(conj for _, conj in run[1:]):
                out.append(_hit("asyndeton", start, joined, f"{len(run)} members"))
    return out


def _opener(ws):
    if not ws:
        return ""
    first = X.norm(ws[0])
    return " ".join(X.norm(w) for w in ws[:2]) if first in X.ARTICLES else first


def anaphora(sents):
    out = []
    units = [[(st, X.words(s)) for st, s in sents]]
    units += [[(st, X.words(c)) for c in clauses(s)] for st, s in sents]
    for seq in units:
        for key in (lambda ws: _opener(ws), lambda ws: _opener(_strip_lead(ws))):
            i = 0
            while i < len(seq):
                k, j = key(seq[i][1]), i + 1
                while k and j < len(seq) and key(seq[j][1]) == k:
                    j += 1
                if k and j - i >= 3 and any(len(ws) > 1 for _, ws in seq[i:j]):
                    out.append(_hit("anaphora", seq[i][0], " | ".join(" ".join(ws[:4]) for _, ws in seq[i:j]),
                                    f"{j - i} open with '{k}'"))
                i = j
    return _dedupe(out)


def polysyndeton(sents):
    out = []
    for start, s in sents:
        ws = [X.norm(w) for w in X.words(s)]
        for conj in ("and", "or", "nor"):
            idx = [i for i, w in enumerate(ws) if w == conj]
            run = 1
            for a, b in zip(idx, idx[1:]):
                run = run + 1 if 1 <= b - a - 1 <= 3 else 1
                if run >= 2:
                    out.append(_hit("polysyndeton", start, s, f"'{conj}' before each member"))
                    break
    return _dedupe(out)


_REPEAT_OK = frozenset({"that", "had", "is", "do", "the", "a", "to", "in", "it"})


def epizeuxis(sents):
    out = []
    for start, s in sents:
        toks = re.findall(r"[A-Za-z']+|[,;]", s)
        ws = [t for t in toks if t not in ",;"]
        for i in range(len(ws) - 1):
            if X.norm(ws[i]) == X.norm(ws[i + 1]):
                n = 2
                while i + n < len(ws) and X.norm(ws[i + n]) == X.norm(ws[i]):
                    n += 1
                if X.norm(ws[i]) not in _REPEAT_OK or n >= 3:
                    out.append(_hit("epizeuxis", start, s, f"'{ws[i]}' x{n}"))
                    break
    return out

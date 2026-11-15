"""Graded survival: how much of each property came through an edit.

The meaning guard says kept or lost for each protected item. CORE asks for a
spectrum: each property carries a clarity value, 1 when the rewrite carries it
as clearly as the original, below 1 for loss, above 1 for gain. This module
reports that spectrum for five property families:

  items     every invariant the meaning guard reads (numbers, quotes, names,
            modals, negations, scope words, citations, code). kept reads 1.0
            and dropped 0.0. A changed value (number, quote, name, citation,
            code) reads 0.0, since a different value is a different fact. A
            changed modal reads 1 minus the step on a strength scale (must 1.0,
            should 0.7, may 0.4), and other changed words read their character
            similarity. Changed items carry `estimated`.
  devices   the rhetorical devices articulate.devices reads, as the count after
            over the count before. 1 means the device survived in kind and
            number, 0 means it is gone, above 1 means the rewrite added it.
  rhythm    sentence-length distribution: 1 minus the two-sample
            Kolmogorov-Smirnov distance, plus the coefficient of variation
            before and after.
  order     sentences matched across the edit (similarity 0.6 or more), and
            (Kendall tau + 1) / 2 over the matched positions: 1 is the same
            order, 0 the reverse.
  register  rates per 1,000 words of contractions, first and second person,
            nominalisations, and mean word and sentence length; each clarity is
            1 minus the relative change, floored at 0.

Every clarity here is computed by a fixed rule from counts, and the rules are
hand-set (CORE A9: shape measured, weight unmeasured). No clarity changes
whether an edit is accepted. Standard library only.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from statistics import mean, pstdev

from . import devices, meaning

SCHEMA = "articulate/survival/1"
_SENT = re.compile(r"[^.!?\n]+[.!?]*")
_WORD = re.compile(r"[A-Za-z][A-Za-z'’-]*")
_REGISTER = {
    "contractions": re.compile(r"\b\w+['’](?:s|t|re|ve|ll|d|m)\b", re.I),
    "first_person": re.compile(r"\b(?:I|me|my|mine|we|us|our|ours)\b"),
    "second_person": re.compile(r"\b(?:you|your|yours)\b", re.I),
    "nominalisations": re.compile(r"\b\w{4,}(?:tion|ment|ance|ence|ity|ness)s?\b", re.I),
}


def _sentences(text):
    return [s.strip() for s in _SENT.findall(text) if _WORD.search(s)]


def _ratio(a, b):
    if a == 0 and b == 0:
        return 1.0
    if a == 0:
        return None
    return round(b / a, 3)


# Modal strength on one scale, so "must" to "should" reads as a partial loss.
_MODAL = {"must": 1.0, "shall": 0.95, "will": 0.9, "need": 0.9, "required": 1.0,
          "should": 0.7, "ought": 0.7, "can": 0.5, "could": 0.4, "may": 0.4, "might": 0.3}
# A changed value is a different value: no partial credit for looking similar.
_VALUE_KINDS = frozenset({"number", "quote", "citation", "code", "math", "url", "email",
                          "entity", "freeze"})


def _changed_clarity(kind, a, b):
    if kind in _VALUE_KINDS:
        return 0.0
    if kind == "modal":
        sa = _MODAL.get(a.lower().split()[0] if a else "", None)
        sb = _MODAL.get(b.lower().split()[0] if b else "", None)
        if sa is not None and sb is not None:
            return round(1 - abs(sa - sb), 3)
    return round(SequenceMatcher(None, a.lower(), b.lower()).ratio(), 3)


def items(original, rewrite):
    report = meaning.compare(original, rewrite)
    rows, by_kind = [], {}
    for r in report["items"]:
        if r["status"] == "added":
            continue
        if r["status"] == "kept":
            c = 1.0
        elif r["status"] == "dropped":
            c = 0.0
        else:
            a, b = r.get("before") or {}, r.get("after") or {}
            c = _changed_clarity(r["kind"], str(a.get("text", "")), str(b.get("text", "")))
        rows.append({"kind": r["kind"], "status": r["status"], "clarity": c,
                     "estimated": r["status"] == "changed"})
        by_kind.setdefault(r["kind"], []).append(c)
    return {"items": rows,
            "kinds": {k: round(mean(v), 3) for k, v in sorted(by_kind.items())},
            "added": report["counts"].get("added", 0)}


def device_survival(original, rewrite):
    a, b = devices.analyze(original)["counts"], devices.analyze(rewrite)["counts"]
    return {d: {"before": a[d], "after": b[d], "clarity": _ratio(a[d], b[d])}
            for d in devices.DEVICES if a[d] or b[d]}


def _ks(xs, ys):
    if not xs or not ys:
        return None
    grid = sorted(set(xs) | set(ys))
    return max(abs(sum(x <= g for x in xs) / len(xs) - sum(y <= g for y in ys) / len(ys))
               for g in grid)


def _cv(xs):
    return round(pstdev(xs) / mean(xs), 3) if len(xs) > 1 and mean(xs) else None


def rhythm(original, rewrite):
    la = [len(_WORD.findall(s)) for s in _sentences(original)]
    lb = [len(_WORD.findall(s)) for s in _sentences(rewrite)]
    ks = _ks(la, lb)
    return {"sentences_before": len(la), "sentences_after": len(lb),
            "cv_before": _cv(la), "cv_after": _cv(lb),
            "clarity": None if ks is None else round(1 - ks, 3)}


def _tau(pos):
    n = len(pos)
    if n < 2:
        return None
    conc = disc = 0
    for i in range(n):
        for j in range(i + 1, n):
            s = (pos[j] - pos[i])
            conc += s > 0
            disc += s < 0
    return (conc - disc) / (n * (n - 1) / 2)


def order(original, rewrite):
    sa, sb = _sentences(original), _sentences(rewrite)
    used, pos = set(), []
    for s in sa:
        best, at = 0.0, None
        for j, t in enumerate(sb):
            if j in used:
                continue
            r = SequenceMatcher(None, s.lower(), t.lower()).ratio()
            if r > best:
                best, at = r, j
        if at is not None and best >= 0.6:
            used.add(at)
            pos.append(at)
    tau = _tau(pos)
    return {"matched": len(pos), "of": len(sa),
            "clarity": None if tau is None else round((tau + 1) / 2, 3)}


def _register(text):
    words = _WORD.findall(text)
    n = len(words) or 1
    sents = _sentences(text) or [text]
    out = {k: len(rx.findall(text)) / n * 1000 for k, rx in _REGISTER.items()}
    out["mean_word_length"] = mean(len(w) for w in words) if words else 0.0
    out["mean_sentence_length"] = n / len(sents)
    return out


def register(original, rewrite):
    a, b = _register(original), _register(rewrite)
    feats = {}
    for k in a:
        top = max(a[k], b[k])
        c = 1.0 if top == 0 else max(0.0, 1 - abs(a[k] - b[k]) / top)
        feats[k] = {"before": round(a[k], 2), "after": round(b[k], 2), "clarity": round(c, 3)}
    return {"features": feats, "clarity": round(mean(f["clarity"] for f in feats.values()), 3)}


def compare(original, rewrite):
    """The survival spectrum of `rewrite` against `original`."""
    it = items(original, rewrite)
    return {"schema": SCHEMA, "items": it, "devices": device_survival(original, rewrite),
            "rhythm": rhythm(original, rewrite), "order": order(original, rewrite),
            "register": register(original, rewrite),
            "scope": "Clarity by fixed rules from counts; hand-set rules, not calibrated "
                     "against readers. It reports and never decides acceptance."}


def format_lines(rep):
    """Readable lines for the change report."""
    out = []
    kinds = rep["items"]["kinds"]
    if kinds:
        out.append("  survival, items: " + ", ".join(f"{k} {v:.2f}" for k, v in kinds.items()))
    if rep["devices"]:
        out.append("  survival, devices: " + ", ".join(
            f"{d} {v['before']}->{v['after']}" for d, v in rep["devices"].items()))
    rh, od, rg = rep["rhythm"], rep["order"], rep["register"]
    out.append(f"  survival, rhythm {rh['clarity']}, order {od['clarity']} "
               f"({od['matched']}/{od['of']} sentences matched), register {rg['clarity']}")
    return out

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
articulate.meaning -- the meaning guard: does a rewrite keep the original's
surface facts?

`compare(original, rewrite)` extracts the invariants of both texts (see
articulate.invariants) and pairs them by normalized key, kind by kind, in
document order. Each invariant is reported as:

  kept     the same key appears in both texts.
  dropped  it is in the original and missing from the rewrite.
  added    it is in the rewrite and was not in the original.
  changed  an unmatched original item and an unmatched rewrite item of the same
           kind, paired in order: "10 ms" became "20 ms", "must" became "should".

The verdict is `preserved` when every invariant is kept, else `changed`.

What it does not prove: the invariants are surface proxies. A rewrite can keep
every one and still change the meaning, for example by moving a negation into
another clause, swapping the order of two numbers, or changing a word no
invariant covers. A reported change can also be harmless. A `preserved` verdict
is a screen, never a proof that two texts say the same thing. Standard library only.
"""
from __future__ import annotations

import bisect
import re

from . import invariants

SCHEMA = "articulate/meaning/v2"
SCOPE = (
    "Compares the surface markers of two texts: numbers, names, negations and the "
    "other invariant kinds. A capitalized word that opens a sentence counts as a "
    "name only when the text also uses it as a name mid-sentence. 'preserved' "
    "means every marker matches. Read the rewrite to confirm the meaning.")
STATUSES = ("kept", "dropped", "added", "changed")
# Negation has a single key, so an unmatched pair of negations cannot be a change
# of value; it is a count change, reported as dropped or added.
_PAIRED = frozenset(k for k in invariants.KINDS if k != "negation")
_LOWER_WORD = re.compile(r"\b[a-z]+\b")


def _locator(text):
    starts = [0] + [i + 1 for i, c in enumerate(text) if c == "\n"]

    def at(offset):
        i = bisect.bisect_right(starts, offset) - 1
        return i + 1, offset - starts[i] + 1
    return at


def _side(item, at):
    if item is None:
        return None
    line, col = at(item["start"])
    return {"text": item["text"], "key": item["key"], "line": line, "col": col,
            "start": item["start"], "end": item["end"]}


def _promote_names(original, rewrite, items):
    """A capitalized word that opens a sentence is weak, since it may be an
    ordinary word. It counts as a name when either text also uses it as a name
    mid-sentence, outside a heading, and neither text uses it in lower case. A
    title-case heading ("Quick Start") is no evidence, and neither is a word
    the text also writes as "start"."""
    names = [i for i in items if i["kind"] == "entity"]
    evidence = {i["key"] for i in names if not i["weak"] and not i["heading"]}
    lower = set(_LOWER_WORD.findall(original)) | set(_LOWER_WORD.findall(rewrite))
    for i in names:
        if i["weak"] and i["key"] in evidence and i["key"].lower() not in lower:
            i["weak"] = False


def _match(a, b):
    """Pair one kind's items by key. Strong items claim a partner first, and a
    strong partner is preferred; an unmatched weak item (a capitalized word at a
    sentence start) is not reported, because it may be an ordinary word."""
    pool = {}
    for j in sorted(range(len(b)), key=lambda j: (b[j].get("weak", False), j)):
        pool.setdefault(b[j]["key"], []).append(j)
    pairs, dropped, used = [], [], set()
    for i in sorted(range(len(a)), key=lambda i: (a[i].get("weak", False), i)):
        slots = pool.get(a[i]["key"])
        if slots:
            j = slots.pop(0)
            used.add(j)
            pairs.append((a[i], b[j]))
        elif not a[i].get("weak"):
            dropped.append(a[i])
    added = [it for j, it in enumerate(b) if j not in used and not it.get("weak")]
    pairs.sort(key=lambda p: p[0]["start"])
    dropped.sort(key=lambda it: it["start"])
    return pairs, dropped, added


def _compare_kind(kind, a, b, at_a, at_b):
    pairs, dropped, added = _match(a, b)
    out = [{"kind": kind, "status": "kept", "before": _side(x, at_a),
            "after": _side(y, at_b)} for x, y in pairs]
    n = min(len(dropped), len(added)) if kind in _PAIRED else 0
    for x, y in zip(dropped[:n], added[:n]):
        out.append({"kind": kind, "status": "changed", "before": _side(x, at_a),
                    "after": _side(y, at_b)})
    out += [{"kind": kind, "status": "dropped", "before": _side(x, at_a),
             "after": None} for x in dropped[n:]]
    out += [{"kind": kind, "status": "added", "before": None,
             "after": _side(y, at_b)} for y in added[n:]]
    return out


def compare(original, rewrite, *, freeze=(), tex=False, quotes=True):
    """The meaning-guard report for a rewrite of `original`. `tex` reads both
    texts as .tex files, as the protected-span layer does. `quotes` off reads
    quoted material as prose, for quotes the model was allowed to edit."""
    a_items = invariants.extract(original, freeze=freeze, tex=tex, quotes=quotes)
    b_items = invariants.extract(rewrite, freeze=freeze, tex=tex, quotes=quotes)
    _promote_names(original, rewrite, a_items + b_items)
    at_a, at_b = _locator(original), _locator(rewrite)
    items, by_kind = [], {}
    for kind in invariants.KINDS:
        a = [i for i in a_items if i["kind"] == kind]
        b = [i for i in b_items if i["kind"] == kind]
        rows = _compare_kind(kind, a, b, at_a, at_b)
        items.extend(rows)
        if rows:
            by_kind[kind] = {s: sum(1 for r in rows if r["status"] == s) for s in STATUSES}
    counts = {s: sum(1 for r in items if r["status"] == s) for s in STATUSES}
    changed = counts["dropped"] + counts["added"] + counts["changed"]
    return {"schema": SCHEMA, "verdict": "changed" if changed else "preserved",
            "counts": counts, "by_kind": by_kind, "items": items,
            "scope": SCOPE}


def blocking(report, allow=()):
    """The non-kept items whose kind is not allowed to change."""
    allow = set(allow)
    return [r for r in report["items"]
            if r["status"] != "kept" and r["kind"] not in allow]


def describe_item(r):
    before, after = r["before"], r["after"]
    if r["status"] == "changed":
        return (f"changed {r['kind']} {before['text']!r} (L{before['line']}) -> "
                f"{after['text']!r} (L{after['line']})")
    side = before or after
    return f"{r['status']} {r['kind']} {side['text']!r} (L{side['line']})"


def describe(rows, limit=5):
    """A one-line summary of the blocking items, for a refusal message."""
    text = "; ".join(describe_item(r) for r in rows[:limit])
    if len(rows) > limit:
        text += f"; and {len(rows) - limit} more"
    return text


def format_report(report, show_kept=False):
    """The human-readable report: a verdict line, one line per non-kept item,
    and a line on what the checks cover."""
    c = report["counts"]
    lines = [f"[meaning] {report['verdict']}: {c['kept']} kept, {c['dropped']} dropped, "
             f"{c['added']} added, {c['changed']} changed"]
    for r in report["items"]:
        if r["status"] == "kept" and not show_kept:
            continue
        lines.append(f"  {r['status']:<8} {r['kind']:<9} " + _where(r))
    lines.append("[meaning] These checks cover numbers, names, negations and other "
                 "surface markers. Read the rewrite to confirm the meaning.")
    return "\n".join(lines)


def _where(r):
    parts = []
    for side in (r["before"], r["after"]):
        if side is not None:
            parts.append(f"L{side['line']}:{side['col']} {side['text']!r}")
    return " -> ".join(parts)

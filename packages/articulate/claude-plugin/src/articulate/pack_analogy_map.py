#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
articulate.pack_analogy_map -- analogies in research point at a map (rule pack `analogy-map`).

  analogy-untested (LOW)   an analogy that carries structure, and so carries
                           an argument, with no pointer to a testable map in
                           its sentence or the next: what corresponds to what,
                           where the map breaks, a prediction through it, or a
                           link to the work that tests it.

In research and publication writing a cross-domain analogy that carries the
argument should become a map that can fail: corresponding quantities, a range
of validity, a held-out prediction, a stated way to break. This is advice. It
reports in the LOW tier and never gates, and a stock comparison with nothing
mapped is left to the device report. The pointer is read by its words
(articulate.analogy.points_at_map), so a map named in prose and never built
still reads as a pointer. Standard library only.
"""
from __future__ import annotations

from . import analogy
from .pack_devices import _prose_text

NAME = "analogy-map"
CATEGORIES = ("analogy-untested",)
OPTIONS = {}


def scan(text, prose, opts, make):
    found = {"HIGH": [], "MEDIUM": [], "LOW": []}
    starts = {rec[0]: rec for rec in prose}
    masked = _prose_text(text, prose)
    for hit in analogy.find(masked):
        if hit["verdict"] != "carries" or hit["map"]:
            continue
        line = masked.count("\n", 0, hit["start"]) + 1
        if line not in starts:
            continue
        line_no, off, raw, _m = starts[line]
        col = max(0, hit["start"] - off)
        end = min(len(raw.rstrip("\r\n")), col + len(hit["snippet"]))
        found["LOW"].append(make(
            line_no, off, "analogy-untested",
            f"analogy carries the argument ({hit['detail']}) and points at no testable map; "
            f"name what corresponds, where it breaks, or what it predicts",
            col, max(end, col), raw, raw.strip()[:100]))
    return found


def fingerprint():
    return [analogy._FRAME.pattern, analogy._PAIR.pattern, analogy._RELATION.pattern,
            analogy._MAP.pattern, repr(sorted(analogy.STOCK_COMPARISON))]

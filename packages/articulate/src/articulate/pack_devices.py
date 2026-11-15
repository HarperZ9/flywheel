#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
articulate.pack_devices -- literary devices judged by the work they do (rule pack `literary-devices`).

  device-empty (LOW)   a device (anaphora, tricolon, antithesis, metaphor and
                       the rest) whose sentence carries no image, no anchor
                       and no stance, or whose figure rests on a stock vehicle.

The pack judges the figures machine-default prose leans on (antithesis,
tricolon, anaphora, asyndeton, chiasmus, epizeuxis, metaphor, simile). Sound
and balance shapes (alliteration, assonance, isocolon and the rest) turn up in
any prose by chance, so they are named in the report and never flagged.
A device that carries an image, an anchor or a stance raises nothing here: in
the author-voice and narrative registers it is a tool. articulate.device_function
names every device with its reading, and `articulate devices --function` prints
the full list. Standard library only.
"""
from __future__ import annotations

from . import device_function

NAME = "literary-devices"
CATEGORIES = ("device-empty",)
OPTIONS = {}


def _prose_text(text, prose):
    """The document with every non-prose line blanked, so offsets still match."""
    keep = {rec[0]: rec[3] for rec in prose}
    out = []
    for n, line in enumerate(text.splitlines(keepends=True), 1):
        body = keep.get(n)
        if body is None:
            out.append("".join(c if c in "\r\n" else " " for c in line))
        else:
            out.append(body + line[len(body):])
    return "".join(out)


def scan(text, prose, opts, make):
    found = {"HIGH": [], "MEDIUM": [], "LOW": []}
    starts = {rec[0]: rec for rec in prose}
    masked = _prose_text(text, prose)
    by_line = {}
    for row in device_function.analyze(masked)["devices"]:
        if (row["verdict"] == "empty" and row["device"] in device_function.JUDGED
                and row["line"] in starts):
            by_line.setdefault(row["line"], []).append(row)
    for line, rows in sorted(by_line.items()):
        line_no, off, raw, _m = starts[line]
        col = max(0, min(r["start"] for r in rows) - off)
        names = ", ".join(sorted({r["device"] for r in rows}))
        stock = sorted({w for r in rows for w in r["stock"]})
        stock = f", stock vehicle {', '.join(stock)}" if stock else ""
        label = f"{names} with no image, anchor or stance{stock}; give it a load or cut it"
        end = min(len(raw.rstrip("\r\n")), col + max(len(r["snippet"]) for r in rows))
        found["LOW"].append(make(line_no, off, "device-empty", label, col, max(end, col), raw,
                                 raw.strip()[:100]))
    return found


def fingerprint():
    from . import imagery_lex as L
    return ["IMAGE=%d" % len(L.IMAGE), repr(sorted(L.IMAGE)), repr(sorted(L.SENSE)),
            repr(sorted(L.STOCK)), L.STOCK_PHRASES.pattern, L.ANCHOR.pattern, L.STANCE.pattern]

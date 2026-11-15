"""Measured re-tiering of detector findings, outside the pinned ruleset.

The detector's rules and tiers are byte-pinned (scripts/check_release_ruleset.py),
so a correction that the evidence supports lives here, after the detector and
before the gate. Each correction moves a finding between tiers and labels why.
No finding is dropped: a moved finding is still reported, so the signal stays
visible to the writer.

calibration/1 makes two corrections.

  filler-intensifier  HIGH to LOW (report only). The 0.4.1 audit and the 0.16.0
                      re-run found it fires on 26 of 91 TOEFL learner texts
                      against 2 of 70 length-matched US college essay windows,
                      a per-word ratio of 10.6, and HIGH blocks under the default
                      profile. Demoting it removed the gap on a held-out half
                      (9/45 against 7/35 blocked) and left the AI recall of the
                      known-provenance corpus unchanged (71/84). The trail is in
                      docs/calibration.md. A profile that wants it to block names
                      it in `gate_promote`.

  attributed quotes   a HIGH or MEDIUM finding that sits wholly inside a
                      quotation attributed to someone (a speech or citation verb
                      beside the quote) moves to LOW with the label prefix
                      "quoted:". The words are the quoted writer's, so they do
                      not gate the person quoting them. A quote that is most of
                      its paragraph, or that has no attribution, is left alone,
                      so wrapping one's own prose in quotation marks changes
                      nothing.

Standard library only.
"""
from __future__ import annotations

import re

from . import masking

VERSIONS = ("calibration/1",)
VERSION = VERSIONS[-1]

DEMOTE_CATEGORIES = frozenset({"filler-intensifier"})
_ATTR_VERB = (r"(?:said|says|say|wrote|writes|write|argued|argues|argue|asked|asks|"
              r"told|tells|claimed|claims|claim|called|calls|insisted|insists|"
              r"replied|replies|added|adds|noted|notes|warned|warns|put it|"
              r"according to|in the words of|quoted|declared|declares)")
_BEFORE = re.compile(_ATTR_VERB + r"\b[^\"“‘.!?]{0,40}$|:\s*$", re.I)
_AFTER = re.compile(r"^[,.]?\s*(?:\w+\s+){0,3}" + _ATTR_VERB + r"\b", re.I)
MAX_QUOTE_SHARE = 0.6
_QUOTED = re.compile(masking.QUOTED_PATTERN)


def _paragraph_bounds(text, pos):
    start = text.rfind("\n\n", 0, pos)
    end = text.find("\n\n", pos)
    return (0 if start < 0 else start + 2), (len(text) if end < 0 else end)


def attributed_quotes(text):
    """(start, end) of each quotation with an attribution beside it, where the
    quote is under MAX_QUOTE_SHARE of its paragraph's characters."""
    spans = []
    for m in _QUOTED.finditer(text):
        a, b = m.span()
        pa, pb = _paragraph_bounds(text, a)
        para_len = len(text[pa:pb].strip()) or 1
        if (b - a) / para_len >= MAX_QUOTE_SHARE:
            continue
        before = text[max(pa, a - 60):a]
        after = text[b:min(pb, b + 40)]
        if _BEFORE.search(before) or _AFTER.search(after):
            spans.append((a, b))
    return spans


def _inside(f, spans):
    return any(a <= f["start"] and f["end"] <= b for a, b in spans)


def _move(f, tier, prefix=""):
    g = dict(f)
    g["tier"] = tier
    if prefix:
        g["label"] = prefix + g["label"]
    return g


def apply(result, text, version=VERSION):
    """Re-tier `result` in place for `text`. Returns True when anything moved.
    The caller recomputes the gate."""
    if version not in VERSIONS:
        raise ValueError(f"unknown calibration {version!r}")
    quotes = attributed_quotes(text)
    moved = []
    for key in ("high", "medium"):
        keep = []
        for f in result[key]:
            if f["category"] in DEMOTE_CATEGORIES:
                moved.append(_move(f, "LOW", "report only: "))
            elif quotes and _inside(f, quotes):
                moved.append(_move(f, "LOW", "quoted: "))
            else:
                keep.append(f)
        result[key] = keep
    if moved:
        result["low"] = result["low"] + moved
    return bool(moved)

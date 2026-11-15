#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""articulate.desk_field -- the "Across the field" half of the desk.

Fixed questions for the human reviewer about what the work adds to its field.
Articulate fills in nothing here: no model output, no score, no ranking, no
citation count and no novelty or impact measure. Where the document itself
states a contribution, related work or future work, the desk quotes those
sentences beside the matching question, each labeled as the authors' claim.

Standard library only.
"""
from __future__ import annotations

import re

from .logical import sentences, units

LABEL = "the authors' claim, not an assessment"
_COMMENT = re.compile(r"<!--.*?-->", re.S)
PROMPTS = (
    ("learn", "What does this work let us learn that we did not know before?"),
    ("change", "How does it change how the field should think about the problem?"),
    ("future", "What future work does it make possible, and what does it rule out?"),
    ("prior", "Which closest prior work does it build on, contradict or supersede, and "
              "does it say so?"),
    ("matters", "If every local claim holds, does the contribution still matter?"),
)
_CUES = {
    "learn": re.compile(r"(?i)\b(?:we (?:contribute|introduce|present|propose)|our "
                        r"contributions? (?:is|are)|this (?:paper|work|study) "
                        r"(?:contributes|introduces|presents|proposes))\b"),
    "change": re.compile(r"(?i)\b(?:we show that|this (?:changes|challenges|overturns)|"
                         r"contrary to (?:the )?(?:common|prevailing) view)\b"),
    "prior": re.compile(r"(?i)\b(?:prior work|previous work|related work|unlike|"
                        r"in contrast to|builds? on|extends? the)\b"),
    "future": re.compile(r"(?i)\b(?:future work|we leave|could (?:extend|be extended)|"
                         r"opens? the way|enables? future)\b"),
}
_SECTION_KIND = (("related work", "prior"), ("prior work", "prior"), ("background", "prior"),
                 ("future work", "future"), ("contribution", "learn"))


def _heading_kind(text):
    low = text.lower()
    for key, kind in _SECTION_KIND:
        if key in low:
            return kind
    return None


def without_comments(text):
    """The text with HTML comments blanked, line breaks and offsets kept."""
    return _COMMENT.sub(lambda m: "".join(c if c == "\n" else " " for c in m.group(0)), text)


def claims(text):
    """{prompt id: [sentences quoted from the document]} in document order."""
    found = {pid: [] for pid, _q in PROMPTS}
    section = None
    for u in units(without_comments(text).splitlines(keepends=True)):
        if u.kind == "heading":
            section = _heading_kind(u.text)
            continue
        if u.kind in ("quote", "hr", "tablesep", "table"):
            continue
        for s, e in sentences(u.text):
            sent = u.text[s:e].strip()
            kinds = {k for k, rx in _CUES.items() if rx.search(sent)}
            if section:
                kinds.add(section)
            for k in kinds:
                if sent not in found[k]:
                    found[k].append(sent)
    return found


def across_field(text):
    found = claims(text)
    return {"prompts": [{"id": pid, "question": q,
                         "authors_claims": [{"quote": s[:240], "label": LABEL}
                                            for s in found[pid]]}
                        for pid, q in PROMPTS]}, found

#!/usr/bin/env python3
"""structural.py -- report-only detectors for rhetorical structure.

The phrase-list engine in check.py sees vocabulary. Several tells named in the
writing standard live in structure instead, so a draft can score a clean
per100w and still read as machine prose: the rule of three (tricolon), negative
anaphora, and the short landing sentence that seals a paragraph. This module
counts those, and reports a sentence-length cadence metric so a suspiciously
even beat is visible. Corrective negation (antithesis) moved to higher_order.py,
which carries the richer clause-level and adjacent-sentence version.

Every category here is a heuristic, so it is REPORT-ONLY: it informs a writer
and never gates, the same contract the Phase 2 checks in check.py follow.
Standard library only.
"""
from __future__ import annotations

import math
import re

_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")

# "A, B, and C" / "A, B, or C": three short items (each 1 to 3 words), Oxford
# comma optional. Catches the tricolon a model reaches for by reflex.
_RULE_OF_THREE = re.compile(
    r"\b[\w'-]+(?:\s+[\w'-]+){0,2},\s+[\w'-]+(?:\s+[\w'-]+){0,2},?"
    r"\s+(?:and|or)\s+[\w'-]+(?:\s+[\w'-]+){0,2}\b",
    re.IGNORECASE)

# Negative anaphora: "no X, no Y" (often continued, "no key, no clock").
_NEG_ANAPHORA = re.compile(r"\bno\s+[\w'-]+,\s+no\s+[\w'-]+", re.IGNORECASE)


def _wc(text: str) -> int:
    return len(_WORD.findall(text))


def structural_counts(prose: str, paras: "list[str]", sentences_of) -> dict:
    """Return report-only structural violation counts for `prose`.

    `sentences_of` is check.py's sentence splitter, passed in so paragraph
    landing-sentence detection uses the same segmentation as the rest.
    """
    v: "dict[str, int]" = {}
    r3 = len(_RULE_OF_THREE.findall(prose))
    if r3:
        v["rule_of_three"] = r3
    na = len(_NEG_ANAPHORA.findall(prose))
    if na:
        v["negative_anaphora"] = na

    landing = 0
    for para in paras:
        psents = sentences_of(para)
        if len(psents) < 3:
            continue
        prior = [_wc(s) for s in psents[:-1]]
        last = _wc(psents[-1])
        mean_prior = sum(prior) / len(prior) if prior else 0.0
        # A short declarative sealing a paragraph after longer sentences.
        if 0 < last <= 7 and mean_prior and last <= 0.6 * mean_prior:
            landing += 1
    if landing:
        v["landing_sentence"] = landing
    return v


def cadence_cv(sents: "list[str]") -> "float | None":
    """Coefficient of variation of sentence lengths, or None if too few.

    Human prose varies sentence length; a low value (roughly under 0.45) reads
    as an even, machine-like beat. This is an informational metric, not a
    counted violation.
    """
    lens = [n for n in (_wc(s) for s in sents) if n > 0]
    if len(lens) < 5:
        return None
    mean = sum(lens) / len(lens)
    if mean == 0:
        return None
    var = sum((n - mean) ** 2 for n in lens) / len(lens)
    return round(math.sqrt(var) / mean, 2)

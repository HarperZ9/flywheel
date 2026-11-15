#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
articulate.pack_plain -- the plain-language rule pack (profile `plain-language`).

  plain-readability (MEDIUM)   the document's Flesch-Kincaid grade is above the
                               target. The finding anchors on the hardest
                               sentence. Under the strict profile it gates.
  plain-long-sentence (LOW)    a sentence over 25 words.
  plain-wordy (LOW)            a wordy phrase with a plainer form, such as "in
                               order to" for "to", with the suggestion.

The grade uses the Flesch-Kincaid formula, 0.39 x (words per sentence) + 11.8 x
(syllables per word) - 15.59, and the report adds Flesch reading ease, 206.835 -
1.015 x (words per sentence) - 84.6 x (syllables per word). Both come from
Kincaid et al. (1975) as reproduced on Microsoft's Word readability help page.

Where the defaults come from. Grade 8: Microsoft Word's readability help says the
recommended grade score is "around 7.0 to 8.0". No US federal rule sets a number:
the Plain Writing Act of 2010 defines plain writing without a score, and the
Federal Plain Language Guidelines argue against a blanket grade. Health guidance
aims lower (AHRQ recommends grade 4 to 6 for patient materials), so a health team
should set `max_grade` to 6. 25 words: GOV.UK's writing guidance splits sentences
over 25 words. 100 words: Articulate's own floor, because a grade computed on a
few sentences swings widely; below it the gate stays silent. The wordy-phrase
list is curated for this tool.

The syllable count is a heuristic (see pack_util), so the grade is an estimate
and can differ from another tool's by a grade or more. A low grade shows short
words and sentences; it cannot show that a reader understands the text. English
only. Standard library only.
"""
from __future__ import annotations

import re

from . import pack_util

NAME = "plain-language"
CATEGORIES = ("plain-readability", "plain-long-sentence", "plain-wordy")
OPTIONS = {"max_grade": 8.0, "min_words": 100, "max_sentence_words": 25}

_WORDY = [(p, s) for p, s in (
    ("in order to", "to"), ("utilize", "use"), ("utilization", "use"),
    ("prior to", "before"), ("subsequent to", "after"), ("in the event that", "if"),
    ("at this point in time", "now"), ("due to the fact that", "because"),
    ("in spite of the fact that", "although"), ("with regard to", "about"),
    ("with respect to", "about"), ("commence", "start"), ("terminate", "end"),
    ("facilitate", "help"), ("approximately", "about"), ("sufficient", "enough"),
    ("additional", "more"), ("assist", "help"), ("demonstrate", "show"),
    ("endeavor", "try"), ("obtain", "get"), ("purchase", "buy"),
    ("is able to", "can"), ("has the ability to", "can"),
    ("for the purpose of", "to, or for"), ("on a daily basis", "daily"),
    ("in close proximity to", "near"), ("until such time as", "until"),
    ("notwithstanding", "despite"), ("pursuant to", "under"),
    ("henceforth", "from now on"), ("in accordance with", "under, or by"))]
_WORDY_RX = re.compile(r"(?i)\b(" + "|".join(re.escape(p) for p, _s in _WORDY) + r")\b")
_SUGGEST = {p: s for p, s in _WORDY}


def _counts(text):
    ws = pack_util.words(text)
    return len(ws), sum(pack_util.syllables(w) for w in ws)


def grade_and_ease(n_sent, n_words, n_syll):
    """(Flesch-Kincaid grade, Flesch reading ease)."""
    wps, spw = n_words / n_sent, n_syll / n_words
    return 0.39 * wps + 11.8 * spw - 15.59, 206.835 - 1.015 * wps - 84.6 * spw


def _readability(sents, opts, make):
    scored = [(s, *_counts(s["text"])) for s in sents]
    scored = [row for row in scored if row[1] >= 3]
    n_words = sum(r[1] for r in scored)
    if not scored or n_words < opts["min_words"]:
        return None
    grade, ease = grade_and_ease(len(scored), n_words, sum(r[2] for r in scored))
    if grade <= opts["max_grade"]:
        return None
    hardest = max(scored, key=lambda r: grade_and_ease(1, r[1], r[2])[0] if r[1] >= 8 else -99)
    label = (f"reading grade {grade:.1f} is above the target {opts['max_grade']:g} "
             f"(Flesch-Kincaid over {len(scored)} sentences and {n_words} words; reading "
             f"ease {ease:.0f}); the hardest sentence starts here")
    return pack_util.finding(make, hardest[0], "plain-readability", label)


def scan(text, prose, opts, make):
    found = pack_util.empty()
    sents = pack_util.sentences(prose)
    worst = _readability(sents, opts, make)
    if worst:
        found["MEDIUM"].append(worst)
    for s in sents:
        n = len(pack_util.words(s["text"]))
        if n > opts["max_sentence_words"]:
            found["LOW"].append(pack_util.finding(
                make, s, "plain-long-sentence",
                f"{n}-word sentence; split it at {opts['max_sentence_words']} words or fewer"))
    for line_no, off, raw, masked in prose:
        for m in _WORDY_RX.finditer(masked):
            phrase = m.group(1).lower()
            found["LOW"].append(make(line_no, off, "plain-wordy",
                                     f"wordy phrase; plainer: {_SUGGEST[phrase]!r}",
                                     m.start(), m.end(), raw, raw.strip()[:100]))
    return found


def fingerprint():
    return [_WORDY_RX.pattern, repr(sorted(_SUGGEST.items())), "fk=0.39,11.8,-15.59",
            "fre=206.835,-1.015,-84.6"]

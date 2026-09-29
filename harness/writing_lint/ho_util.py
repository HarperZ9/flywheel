#!/usr/bin/env python3
"""ho_util.py -- shared backbone for the higher-order tell detectors.

A shallow, stdlib-only tokenizer, light stemmer, and coarse part-of-speech
tagger the detectors in higher_order.py and ho_frames.py read. It is not a real
tagger: it separates function words from content words and spots verb-led
against noun-led runs. Every reader of it is report-only, so a misread informs
a writer rather than gating. Standard library only.
"""
from __future__ import annotations

import re

from .lists import (
    AUX_BE, CONJUNCTIONS, DETERMINERS, ENUM_VERBS, PREPOSITIONS, PRONOUNS,
    STOPWORDS, WH_WORDS,
)

WORD = re.compile(r"[A-Za-z][A-Za-z'’-]*")
FUNCTION = (DETERMINERS | PREPOSITIONS | PRONOUNS | CONJUNCTIONS | AUX_BE
            | WH_WORDS)


def toks(text: str) -> "list[str]":
    return WORD.findall(text)


def wc(text: str) -> int:
    return len(WORD.findall(text))


def stem(word: str) -> str:
    """A light suffix stemmer, enough to line up 'proves' with 'prove'.

    Verb suffixes strip first, then plurals with the usual -ies/-es/-s rules so
    'proves' -> 'prove' (not 'prov') and 'agencies' -> 'agency'.
    """
    w = word.lower()
    if w.endswith(("'s", "’s")):
        w = w[:-2]
    for suf in ("ing", "edly", "ed", "ly"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[: -len(suf)]
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith(("ches", "shes", "sses", "xes", "zes")) and len(w) > 4:
        return w[:-2]
    if w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        return w[:-1]
    return w


def content_stems(sent: str) -> set:
    return {stem(t) for t in toks(sent)
            if t.lower() not in STOPWORDS and len(t) >= 3}


def coarse_pos(tok: str, initial: bool = False) -> str:
    """A shallow part-of-speech tag: function-word classes, then verb/noun.

    `initial` is True for a sentence's first word, so a leading capital is not
    misread as a proper noun. A heuristic backbone, not a real tagger.
    """
    w = tok.lower().strip("'’-")
    if not w:
        return "OTHER"
    if w in WH_WORDS:
        return "WH"
    if w in AUX_BE:
        return "AUX"
    if w in DETERMINERS:
        return "DET"
    if w in PREPOSITIONS:
        return "PREP"
    if w in PRONOUNS:
        return "PRON"
    if w in CONJUNCTIONS:
        return "CONJ"
    if w.isdigit():
        return "NUM"
    if not initial and tok[:1].isupper():
        return "PN"
    if w in ENUM_VERBS or w.endswith(("ing", "ed")):
        return "VERB"
    if w.endswith("ly"):
        return "ADV"
    if w.endswith(("tion", "ment", "ness", "ity", "ies", "ism", "ship",
                   "ance", "ence")):
        return "NOUN"
    if w.endswith("s") and len(w) > 3:
        return "NOUN"
    return "OTHER"


def lead_class(word: str, initial: bool = False) -> str:
    """Collapse coarse_pos to the enumeration lead classes N / V / D."""
    p = coarse_pos(word, initial)
    if p in ("NOUN", "PN", "OTHER"):
        return "N"
    if p == "VERB":
        return "V"
    if p == "DET":
        return "D"
    return p


def phrase_hits(low: str, phrases) -> "list[str]":
    """The phrases from `phrases` that occur in already-lowercased `low`."""
    out = []
    for phrase in phrases:
        if re.search(r"(?<![a-z0-9_])" + re.escape(phrase) + r"(?![a-z0-9_])",
                     low):
            out.append(phrase)
    return out


def longest_band_run(lens, band) -> int:
    """Longest run of consecutive values that all fit inside a `band` window."""
    best = 1 if lens else 0
    i = 0
    for j in range(len(lens)):
        while lens and max(lens[i: j + 1]) - min(lens[i: j + 1]) > band:
            i += 1
        best = max(best, j - i + 1)
    return best


def longest_equal_run(seq) -> int:
    """Longest run of consecutive equal items in `seq`."""
    best = run = 1 if seq else 0
    for a, b in zip(seq, seq[1:]):
        run = run + 1 if a == b else 1
        best = max(best, run)
    return best

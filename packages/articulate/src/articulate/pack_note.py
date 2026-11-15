#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
articulate.pack_note -- a personal note to someone you know (rule pack `note`).

  note-opener (MEDIUM)         a stock opener that clears its throat: "I hope
                               this finds you well", "I wanted to reach out",
                               "I am writing to".
  note-closing-offer (MEDIUM)  a stock closing offer: "let me know if you have
                               any questions", "feel free to reach out", "happy
                               to help", "don't hesitate to".
  note-professional (LOW)      office register in a personal note: "regarding",
                               "per our", "kindly", "at your earliest
                               convenience", "touch base", "best regards".
  note-length (LOW)            the note runs past its word budget (default 120;
                               a note to someone you know reads at about 100).

The `note` domain profile promotes the opener and the closing offer to the
gate, since both are the first things a reader takes as machine text in a
personal note. Length and office words are reported for the writer to weigh.
Each list is closed: a stock phrase worded another way is not caught.
Standard library only.
"""
from __future__ import annotations

import re

from . import pack_util

NAME = "note"
CATEGORIES = ("note-opener", "note-closing-offer", "note-professional", "note-length")
OPTIONS = {"max_words": 120}

_OPENER = re.compile(
    r"(?i)\b(?:I hope (?:this|my) (?:email|message|note|letter)? ?finds you(?: well)?|"
    r"I hope you(?:'re| are) (?:doing )?well|hope you(?:'re| are) doing well|"
    r"I (?:just )?wanted to (?:reach out|touch base|follow up|check in)|I am writing to|"
    r"I'm writing to|I trust this finds you|thank you for (?:taking )?(?:the|your) time)\b")
_CLOSING = re.compile(
    r"(?i)\b(?:(?:please )?let me know if you have any (?:questions|concerns|thoughts)|"
    r"feel free to (?:reach out|contact me|let me know|ask)|(?:I'm|I am|I'd be) (?:more than )?"
    r"happy to help|don'?t hesitate to|do not hesitate to|looking forward to hearing from you|"
    r"I look forward to (?:hearing|your)|hope this helps)\b")
_OFFICE = re.compile(
    r"(?i)\b(?:regarding|per our|kindly|at your earliest convenience|touch base|circle back|"
    r"please find attached|best regards|kind regards|warm regards|I would like to|"
    r"as per|going forward|moving forward)\b")


def _each(prose, rx, category, label, make):
    out = []
    for line_no, off, raw, masked in prose:
        for m in rx.finditer(masked):
            out.append(make(line_no, off, category, label, m.start(), m.end(), raw,
                            raw.strip()[:100]))
    return out


def scan(text, prose, opts, make):
    found = pack_util.empty()
    found["MEDIUM"] += _each(prose, _OPENER, "note-opener",
                             "stock opener; start with the thing you came to say", make)
    found["MEDIUM"] += _each(prose, _CLOSING, "note-closing-offer",
                             "stock closing offer; end when the note is done", make)
    found["LOW"] += _each(prose, _OFFICE, "note-professional",
                          "office register; say it the way you would out loud", make)
    sents = pack_util.sentences(prose)
    n = sum(len(pack_util.words(s["text"])) for s in sents)
    if sents and n > opts["max_words"]:
        found["LOW"].append(pack_util.finding(
            make, sents[0], "note-length",
            f"{n} words; a note to someone you know reads at about 100 "
            f"(budget {opts['max_words']})"))
    return found


def fingerprint():
    return [_OPENER.pattern, _CLOSING.pattern, _OFFICE.pattern]

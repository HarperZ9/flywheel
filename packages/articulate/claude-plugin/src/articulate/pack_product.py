#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
articulate.pack_product -- product copy read from the user's side (rule pack `product-copy`).

  lead-author-framed (MEDIUM)  the first prose sentence of the document talks
                               from the maker's side ("I built", "my tool",
                               "we made") or about what the tool lacks, where
                               a reader looks for what it does for them.
  mission-missing (LOW)        a document of 150 words or more states no
                               mission: no heading named Mission, Why, Purpose
                               or Philosophy, and no sentence that opens with
                               "The mission", "Its mission" or "It exists to".

For the share of words a description spends on what a tool lacks, run
`articulate negation`; that check reads the same documents entry by entry.

The lead reading sees only the first sentence and a closed list of maker-side
openers. A lead can face the reader and still be dull; that call stays with
the writer. Standard library only.
"""
from __future__ import annotations

import re

from . import pack_util

NAME = "product-copy"
CATEGORIES = ("lead-author-framed", "mission-missing")
OPTIONS = {"mission_min_words": 150}

_MAKER = re.compile(
    r"(?i)^(?:so\s+)?(?:i|we)\s+(?:built|made|wrote|created|developed|started|designed|"
    r"wanted|decided|have been)\b|^(?:this is )?(?:my|our) (?:\w+ ){0,2}(?:tool|project|"
    r"library|attempt|take|experiment)\b|^i\b")
_LACK = re.compile(r"(?i)^(?:\S+\s+){0,6}?(?:is not|isn't|does not|doesn't|never|no longer|"
                   r"without|not a|not an)\b")
_MISSION_HEAD = re.compile(r"(?im)^\s{0,3}#{1,6}\s+(?:our |the |its )?(?:mission|why|purpose|"
                           r"philosophy|what (?:it|this) is for)\b")
_MISSION_LINE = re.compile(r"(?i)^(?:the|its|our) mission\b|^(?:it|this tool|this project) "
                           r"exists to\b|^why (?:it|this) exists\b")


def scan(text, prose, opts, make):
    found = pack_util.empty()
    sents = [s for s in pack_util.sentences(prose) if not s["text"].lstrip().startswith("#")]
    if not sents:
        return found
    lead = sents[0]
    body = lead["text"].strip()
    if _MAKER.search(body):
        found["MEDIUM"].append(pack_util.finding(
            make, lead, "lead-author-framed",
            "the lead talks from the maker's side; open on what the tool does for the reader"))
    elif _LACK.search(body):
        found["MEDIUM"].append(pack_util.finding(
            make, lead, "lead-author-framed",
            "the lead opens on what the tool lacks; open on what it does for the reader"))
    n_words = sum(len(pack_util.words(s["text"])) for s in sents)
    has_mission = bool(_MISSION_HEAD.search(text)) or any(
        _MISSION_LINE.search(s["text"].strip()) for s in sents)
    if n_words >= opts["mission_min_words"] and not has_mission:
        found["LOW"].append(pack_util.finding(
            make, lead, "mission-missing",
            f"{n_words} words and no stated mission; add the line that says what the tool is "
            f"for and the idea behind it"))
    return found


def fingerprint():
    return [_MAKER.pattern, _LACK.pattern, _MISSION_HEAD.pattern, _MISSION_LINE.pattern]

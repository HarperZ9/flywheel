#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
articulate.pack_review -- the code review comment rule pack (profile
`code-review`).

A review comment lands on a person. These rules flag wording that makes a
request harder to act on, or that reads as aimed at the author and not the code:

  review-condescension (LOW)     "just", "simply", "obviously", "clearly", "of
                                 course", "trivially": words that tell the
                                 reader the fix is easy. Often innocent ("just a
                                 nit"), so report only.
  review-condescension (MEDIUM)  a stronger marker: "why didn't you", "did you
                                 even", "as everyone knows", "any competent
                                 developer", "not rocket science".
  review-no-reason (LOW)         a request ("please rename", "can you move",
                                 "this should be", "change X to Y") in a comment
                                 that gives no reason anywhere: no "because",
                                 "so that", "to avoid", "otherwise", "since", or
                                 a stated effect.
  review-absolute (MEDIUM)       absolute language about a person: "you always",
                                 "you never", "you keep", "you don't
                                 understand", "your code is wrong".

The profile gates at the flavored level, so these findings report and never
block on their own; the banned devices still gate. Each rule is a phrase list,
so it misses a paraphrase and cannot read tone. English only. Standard library
only.
"""
from __future__ import annotations

import re

from . import pack_util

NAME = "code-review"
CATEGORIES = ("review-condescension", "review-no-reason", "review-absolute")
OPTIONS = {}

_SOFT = re.compile(r"(?i)\b(?:just|simply|obviously|clearly|of course|trivially|easily)\b")
_STRONG = re.compile(
    r"(?i)\bwhy (?:didn't|did not|wouldn't|would|did) you\b|\bdid you (?:even|not)\b"
    r"|\bas everyone knows\b|\bany (?:competent|decent|good|real) (?:developer|engineer|programmer)\b"
    r"|\bnot rocket science\b|\bi(?:'m| am) surprised you\b|\bi can'?t believe\b")
_ABSOLUTE = re.compile(
    r"(?i)\byou (?:always|never|keep|constantly)\b"
    r"|\byou (?:don't|do not|clearly don't|never) (?:understand|get|read|test|think)\b"
    r"|\byour (?:code|change|pr|approach|design) is (?:wrong|bad|terrible|awful|garbage|a mess|sloppy|lazy)\b"
    r"|\byou(?:'re| are) (?:wrong|careless|lazy|sloppy|clueless)\b")
_REQUEST = re.compile(
    r"(?i)^\s*(?:please\s+)?(?:just\s+|simply\s+)?(?:rename|move|remove|delete|add|use|avoid"
    r"|change|replace|extract"
    r"|split|inline|drop|revert|fix|update|simplify)\b"
    r"|\b(?:can|could|would) you\s+(?:please\s+)?\w+"
    r"|\bplease\s+\w+|\b(?:this|it|that) (?:should|needs to|must) (?:be|use|go|return|live)\b")
_REASON = re.compile(
    r"(?i)\b(?:because|since|so that|so we|so it|to avoid|to keep|otherwise|in order to"
    r"|which (?:means|makes|breaks|causes|lets|hides)|this (?:will|would|makes|causes|breaks"
    r"|lets|hides|keeps|leaks|fails)|it (?:will|would|makes|causes|breaks|hides|leaks|fails)"
    r"|for (?:consistency|performance|readability|safety|clarity|correctness)|per the|see )\b")


def _paragraph_sentences(prose):
    """Sentences grouped by comment: a new group at each paragraph start."""
    groups = []
    for s in pack_util.sentences(prose):
        if s["block_start"] or not groups:
            groups.append([])
        groups[-1].append(s)
    return groups


_PHRASES = (
    ("MEDIUM", "review-absolute", _ABSOLUTE,
     "absolute language about a person; describe the code and its effect"),
    ("MEDIUM", "review-condescension", _STRONG,
     "reads as aimed at the author; ask about the code instead"),
    ("LOW", "review-condescension", _SOFT,
     "tells the reader the fix is easy; state the fix and let them judge"),
)


def _phrase_hits(sent, found, make):
    for tier, cat, rx, label in _PHRASES:
        m = rx.search(sent["text"])
        if m:
            found[tier].append(pack_util.finding(make, sent, cat, f"{label}: {m.group(0)!r}"))


def scan(text, prose, opts, make):
    found = pack_util.empty()
    for comment in _paragraph_sentences(prose):
        body = " ".join(s["text"] for s in comment)
        has_reason = bool(_REASON.search(body))
        for sent in comment:
            _phrase_hits(sent, found, make)
            if not has_reason and _REQUEST.search(sent["text"]):
                found["LOW"].append(pack_util.finding(
                    make, sent, "review-no-reason",
                    "a request with no reason in the comment; say what it fixes or prevents"))
    return found


def fingerprint():
    return [rx.pattern for rx in (_SOFT, _STRONG, _ABSOLUTE, _REQUEST, _REASON)]

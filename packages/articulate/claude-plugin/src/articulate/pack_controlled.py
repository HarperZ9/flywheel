#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
articulate.pack_controlled -- controlled English for second-language readers and
machine translation (profile `controlled-english`).

The rules are inspired by controlled-language practice in technical writing.
Articulate does not implement ASD-STE100 or any other controlled-language
specification, ships none of their dictionaries, and makes no conformance claim.
The idiom and phrasal-verb lists here are Articulate's own.

  controlled-sentence-length (MEDIUM)  a sentence over 25 words. Gates under the
                              strict profile.
  controlled-sentence-length (LOW)  an instruction (a sentence that opens with an
                              imperative verb) over 20 words. The instruction
                              check is a heuristic, so this one reports only.
  controlled-multi-instruction (LOW)  an instruction that chains a second
                              imperative with "and", "then", or a semicolon.
                              One instruction per sentence reads and translates
                              more reliably.
  controlled-idiom (LOW)      an idiom a second-language reader or a translation
                              engine may read word by word ("out of the box",
                              "low-hanging fruit"), with a literal alternative.
  controlled-phrasal-verb (LOW)  a phrasal verb with a single-word alternative
                              ("find out" to "learn", "set up" to "configure").
  controlled-vague-pronoun (LOW)  a sentence that opens with "This", "That",
                              "These", or "It" followed by a verb, so the reader
                              must look back for the noun.

Where the defaults come from: 20 words for an instruction and 25 for a
description follow the published sentence-length rules of ASD-STE100 Issue 9
(rules 5.1 and 6.3); both are options. English only. Standard library only.
"""
from __future__ import annotations

import re

from . import pack_util

NAME = "controlled-english"
CATEGORIES = ("controlled-sentence-length", "controlled-multi-instruction",
              "controlled-idiom", "controlled-phrasal-verb", "controlled-vague-pronoun")
OPTIONS = {"max_instruction_words": 20, "max_description_words": 25}

_VERBS = ("add", "apply", "attach", "check", "choose", "click", "close", "configure",
          "connect", "copy", "create", "delete", "disconnect", "do", "download",
          "enable", "disable", "enter", "examine", "find", "install", "keep", "make",
          "measure", "move", "open", "press", "pull", "push", "put", "read", "record",
          "remove", "replace", "restart", "run", "save", "select", "send", "set",
          "start", "stop", "tighten", "turn", "type", "update", "use", "verify", "wait",
          "write", "clean", "compare", "confirm", "loosen", "lift", "hold", "insert")
_VERB_RX = "|".join(_VERBS)
_IMPERATIVE = re.compile(rf"(?i)^(?:(?:first|then|next|now|finally),?\s+)?(?:{_VERB_RX})\b")
_CHAIN = re.compile(rf"(?i)(?:,?\s+and\s+then|,\s*then|;\s*|\s+and)\s+(?:{_VERB_RX})\b")
_VAGUE = re.compile(r"^(?:This|That|These|Those|It)\s+(?:is|was|are|were|means|meant|allows"
                    r"|lets|makes|causes|caused|shows|will|would|can|could|may|might|should"
                    r"|must|has|have|had|does|did|helps|ensures|gives|requires|prevents|keeps"
                    r"|leads|results|breaks|fixes|adds|removes|changes)\b")
_IDIOMS = {
    "out of the box": "by default", "low-hanging fruit": "easy first tasks",
    "on the same page": "in agreement", "touch base": "talk", "in a nutshell": "in short",
    "at the end of the day": "finally", "hit the ground running": "start at once",
    "keep an eye on": "monitor", "rule of thumb": "general guide",
    "the big picture": "the overall view", "under the hood": "internally",
    "boils down to": "comes to", "on the fly": "during operation",
    "back to square one": "back to the start", "a piece of cake": "easy",
    "ballpark figure": "estimate", "cut corners": "skip steps",
    "get the ball rolling": "start", "up in the air": "not decided",
    "in the loop": "informed", "moving forward": "from now on", "a no-brainer": "an easy choice",
    "bells and whistles": "extra features", "by and large": "mostly",
    "spin up": "start", "circle back": "return to",
}
_PHRASAL = {
    "find out": "learn", "set up": "configure", "carry out": "do", "figure out": "determine",
    "look into": "examine", "come up with": "create", "get rid of": "remove",
    "put off": "delay", "go over": "review", "point out": "show", "bring up": "raise",
    "fill out": "complete", "run into": "meet", "take over": "replace", "give up": "stop",
    "check out": "examine", "turn off": "stop", "turn on": "start", "shut down": "stop",
    "make sure": "verify", "look up": "find", "put in": "insert", "take out": "remove",
    "back up": "copy", "hold on": "wait", "go through": "examine", "work out": "calculate",
}


def _phrase_rx(table):
    keys = sorted(table, key=len, reverse=True)
    body = "|".join(r"\s+".join(re.escape(w) for w in k.split()) for k in keys)
    return re.compile(r"(?i)(?<![\w-])(" + body + r")(?![\w-])")


_IDIOM_RX, _PHRASAL_RX = _phrase_rx(_IDIOMS), _phrase_rx(_PHRASAL)


def _sentence_rules(s, opts, found, make):
    n = len(pack_util.words(s["text"]))
    instruction = bool(_IMPERATIVE.match(s["text"]))
    if n > opts["max_description_words"]:
        found["MEDIUM"].append(pack_util.finding(
            make, s, "controlled-sentence-length",
            f"{n}-word sentence; the limit is {opts['max_description_words']}"))
    elif instruction and n > opts["max_instruction_words"]:
        found["LOW"].append(pack_util.finding(
            make, s, "controlled-sentence-length",
            f"{n}-word instruction; the limit is {opts['max_instruction_words']}"))
    if instruction and _CHAIN.search(s["text"]):
        found["LOW"].append(pack_util.finding(
            make, s, "controlled-multi-instruction",
            "two instructions in one sentence; write one instruction per sentence"))
    if _VAGUE.match(s["text"]):
        found["LOW"].append(pack_util.finding(
            make, s, "controlled-vague-pronoun",
            f"opens with {s['text'].split()[0]!r} and a verb; name the thing it refers to"))


def scan(text, prose, opts, make):
    found = pack_util.empty()
    for s in pack_util.sentences(prose):
        _sentence_rules(s, opts, found, make)
    for line_no, off, raw, masked in prose:
        for cat, rx, table in (("controlled-idiom", _IDIOM_RX, _IDIOMS),
                               ("controlled-phrasal-verb", _PHRASAL_RX, _PHRASAL)):
            for m in rx.finditer(masked):
                key = " ".join(m.group(1).lower().split())
                found["LOW"].append(make(line_no, off, cat,
                                         f"{m.group(1)!r} reads literally in translation; "
                                         f"literal form: {table[key]!r}",
                                         m.start(), m.end(), raw, raw.strip()[:100]))
    return found


def fingerprint():
    return [_IMPERATIVE.pattern, _CHAIN.pattern, _VAGUE.pattern,
            repr(sorted(_IDIOMS.items())), repr(sorted(_PHRASAL.items()))]

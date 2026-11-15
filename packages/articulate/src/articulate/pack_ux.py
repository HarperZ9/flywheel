#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
articulate.pack_ux -- the UX microcopy rule pack (profile `ux-microcopy`).

Reads one UI string per line. A line says its type with a prefix
(`button: Save changes`) or through a resource key (`"save_button": "Save
changes",` or `save_button = Save changes`); the key's words decide the type
(button, label, error). Any other line is generic text.

Rules and the source of each default:

  ux-length (MEDIUM)  a button over 3 words or 26 characters; a label over 4
                      words; an error sentence over 25 words. Button words:
                      Material Design 3 button guidelines, "ideally 1-3 words".
                      Button characters: Microsoft Windows button guidance, "a
                      maximum length of 26 characters". Error sentences: GOV.UK
                      writing guidance, which splits sentences over 25 words.
                      Label words: Articulate's own default, with no published
                      number behind it; tune it.
  ux-case (LOW)       a button or label in title case, when the project uses
                      sentence case (Material Design 3 and the Microsoft Style
                      Guide). Apple's guidelines use title-style buttons, so the
                      `case` option takes "sentence", "title", or "off". Report
                      only: a proper noun reads like title case.
  ux-vague-error (LOW)  error text with no next step, where the text is vague
                      ("something went wrong") or states no cause. After the
                      Nielsen Norman Group error-message guidelines: describe
                      the issue and offer a remedy. Report only.
  ux-link-text (MEDIUM)  "click here", or link text such as "here", "this link",
                      or "learn more" that names no destination. After the W3C
                      tip "Don't use 'click here' as link text"; WCAG failure F84
                      applies it at level AAA (success criterion 2.4.9).

Every limit is an option in the project config under "ux-microcopy". English
only. Standard library only.
"""
from __future__ import annotations

import re

from . import pack_util

NAME = "ux-microcopy"
CATEGORIES = ("ux-length", "ux-case", "ux-vague-error", "ux-link-text")
OPTIONS = {"button_max_words": 3, "button_max_chars": 26, "label_max_words": 4,
           "error_max_words": 25, "case": "sentence"}
CHOICES = {"case": ("sentence", "title", "off")}

_PREFIX = re.compile(r"^\s*(?:[-*+]\s+)?(?P<key>[A-Za-z][\w.\-]{0,60})\s*:\s+(?P<text>\S.*?)\s*$")
_KEYVAL = re.compile(r"^\s*[\"']?(?P<key>[\w.\-]{1,80})[\"']?\s*[:=]\s*"
                     r"(?P<q>[\"'])(?P<text>.*?)(?P=q)\s*,?\s*$")
_BULLET = re.compile(r"^\s*(?:[-*+]\s+)?")
_TYPES = (("button", ("button", "btn", "cta", "action", "submit", "confirm")),
          ("error", ("error", "err", "invalid", "fail", "alert")),
          ("label", ("label", "title", "heading", "header", "tab", "menu", "nav", "field")))
_MINOR = {"a", "an", "the", "and", "or", "but", "of", "to", "in", "on", "for", "with",
          "at", "by", "from", "as", "per", "via", "vs"}
_VAGUE = re.compile(r"(?i)\b(?:something went wrong|an?\s(?:unknown\s|unexpected\s)?error"
                    r"(?:\shas)?\soccurred|unknown error|unexpected error|oops|error occurred"
                    r"|invalid (?:input|value|request|data|entry)|(?:operation|request) failed)\b")
_NEXT_STEP = re.compile(r"(?i)\b(?:try|retry|check|enter|choose|select|use|contact|sign in"
                        r"|log in|refresh|reload|restart|wait|make sure|update|remove|add"
                        r"|go to|open|save|confirm|reset|install|call|email|ask|reconnect)\b")
_CAUSE = re.compile(r"(?i)\b(?:because|due to|since|is (?:too|not|missing|empty|already|full)"
                    r"|was not|does not|doesn't|isn't|cannot|can't|expired|too (?:long|short|large|many))\b|\d")
_LINK_TEXT = re.compile(r"(?i)\bclick here\b|\[\s*(?:click here|here|this link|link|more"
                        r"|read more|learn more|this)\s*\]\(")
_HTML_LINK = re.compile(r"(?i)<a\b[^>]{0,400}>\s*(?:click here|here|this link|link|more"
                        r"|read more|learn more)\s*</a>")


def _classify(masked):
    """(type, text, start): the UI string on this line and its type."""
    for rx in (_KEYVAL, _PREFIX):
        m = rx.match(masked)
        if m:
            key = m.group("key").lower()
            for kind, needles in _TYPES:
                if any(n in key for n in needles):
                    return kind, m.group("text"), m.start("text")
            if rx is _KEYVAL:
                return "text", m.group("text"), m.start("text")
    lead = _BULLET.match(masked).end()
    return "text", masked[lead:].rstrip(), lead


def _case_problem(text, want):
    ws = pack_util.words(text)
    major = [w for w in ws[1:] if w.lower() not in _MINOR and not w.isupper()]
    if len(ws) < 2 or not major or want == "off":
        return None
    capital = [w for w in major if w[0].isupper()]
    if want == "sentence" and len(capital) == len(major):
        return "title case in a UI string; this project uses sentence case"
    if want == "title" and len(capital) < len(major):
        return "sentence case in a UI string; this project uses title case"
    return None


def _length_problem(kind, text, opts):
    n, chars = len(pack_util.words(text)), len(text.strip())
    if kind == "button" and (n > opts["button_max_words"] or chars > opts["button_max_chars"]):
        return (f"button label has {n} words and {chars} characters; the limit is "
                f"{opts['button_max_words']} words and {opts['button_max_chars']} characters")
    if kind == "label" and n > opts["label_max_words"]:
        return f"label has {n} words; the limit is {opts['label_max_words']}"
    if kind == "error":
        longest = max((len(pack_util.words(s)) for s in re.split(r"(?<=[.!?])\s+", text)),
                      default=0)
        if longest > opts["error_max_words"]:
            return (f"error message has a {longest}-word sentence; the limit is "
                    f"{opts['error_max_words']} words")
    return None


def _error_problem(kind, text):
    vague = _VAGUE.search(text)
    if _NEXT_STEP.search(text) or not (vague or kind == "error"):
        return None
    if vague or not _CAUSE.search(text):
        return "error text without a cause and a next step: say what happened and what to do"
    return None


def scan(text, prose, opts, make):
    found = pack_util.empty()
    for line_no, off, raw, masked in prose:
        kind, s, start = _classify(masked)
        if not s.strip():
            continue
        end = start + len(s)
        checks = (("MEDIUM", "ux-length", _length_problem(kind, s, opts)),
                  ("LOW", "ux-case", _case_problem(s, opts["case"])
                   if kind in ("button", "label") else None),
                  ("LOW", "ux-vague-error", _error_problem(kind, s)))
        for tier, cat, label in checks:
            if label:
                found[tier].append(make(line_no, off, cat, label, start, end, raw,
                                        raw.strip()[:100]))
        for rx, line in ((_LINK_TEXT, masked), (_HTML_LINK, raw)):
            m = rx.search(line)
            if m:
                found["MEDIUM"].append(make(
                    line_no, off, "ux-link-text",
                    "link text that names no destination; name where the link goes",
                    m.start(), m.end(), raw, raw.strip()[:100]))
                break
    return found


def fingerprint():
    return [rx.pattern for rx in (_PREFIX, _KEYVAL, _VAGUE, _NEXT_STEP, _CAUSE,
                                  _LINK_TEXT, _HTML_LINK)] + [repr(_TYPES), repr(sorted(_MINOR))]

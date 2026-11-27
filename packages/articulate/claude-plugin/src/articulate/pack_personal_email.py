#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
articulate.pack_personal_email -- deterministic AI-email tell checks for short personal mail.

  bulleted_personal_email       (MEDIUM) bulleted or numbered spec-lists inside a short note.
  stiff_template_opener         (MEDIUM) stock corporate openers and bio-pitch openings.
  enumeration_crutch            (MEDIUM) formulaic numbered-preview leads before a list.
  symmetrical_pr_closer         (MEDIUM) canned sign-off offers and flexibility lines.
  parenthetical_metric_stuffing (MEDIUM) dense parenthetical stat packs inside short mail.

The `personal_email` domain profile promotes all five categories to the gate so short
personal replies read like one person writing to another. Standard library only.
"""
from __future__ import annotations

import re

from . import pack_util

NAME = "personal_email"
CATEGORIES = (
    "bulleted_personal_email",
    "stiff_template_opener",
    "enumeration_crutch",
    "symmetrical_pr_closer",
    "parenthetical_metric_stuffing",
)
OPTIONS = {
    "max_short_note_words": 280,
    "min_bullets": 2,
    "min_metric_parens": 2,
}

_BULLET_LINE = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)\S")

_STIFF_OPENER = re.compile(
    r"(?i)(?:"
    r"\bI hope (?:this|my) (?:email|message|note|letter)?\s*finds you(?: well)?\b|"
    r"\bI hope you(?:'re| are) (?:doing )?well\b|"
    r"\bI(?:'m| am) reaching out to\b|"
    r"\bI (?:just )?wanted to reach out\b|"
    r"\bI am writing to (?:express|inquire|share|introduce|follow up)\b|"
    r"\b(?:Hello|Hi|Dear) [^,\n]{1,40}\bteam,\s*I(?:'m| am) (?:a|an)\b|"
    r"\bI am a (?:U\.S\.-citizen-owned|sole proprietor|founder and|software engineer building)\b"
    r")"
)

_ENUM_CRUTCH = re.compile(
    r"(?i)\b(?:"
    r"(?:two|three|four|five|a few) (?:specific|quick|brief|key|short) "
    r"(?:items|things|points|questions|notes|updates)\b|"
    r"here are (?:two|three|four|five|a few) (?:things|points|items|notes)\b"
    r")"
)

_PR_CLOSER = re.compile(
    r"(?i)(?:"
    r"\bthank you for your time and (?:support|consideration|attention)\b|"
    r"\bI am flexible (?:on|with) (?:timing|schedule|dates|hours|times)\b|"
    r"\bplease let me know if you have any (?:questions|concerns|thoughts)\b|"
    r"\bplease do not hesitate to (?:reach out|contact me)\b|"
    r"\bI look forward to (?:hearing from you|connecting soon|your response)\b"
    r")"
)

_PAREN = re.compile(r"\(([^()\n]{4,140})\)")
_NUM_UNIT = re.compile(
    r"(?i)(?:\b\d+(?:[.,/]\d+)*\s*(?:%|ms|s|kb|mb|gb|tb|hz|khz|db|lufs|fps|x|k|m|b|hrs?|pass|tests?|prs?|commits?|repos?|files?)\b|"
    r"\b\d+/\d+\b|"
    r"\$\d[\d,.]*[kmb]?)"
)


def _match_all(prose, rx, category, label, make):
    out = []
    for line_no, off, raw, masked in prose:
        for m in rx.finditer(masked):
            out.append(make(line_no, off, category, label, m.start(), m.end(),
                            raw, raw.strip()[:100]))
    return out


def _scan_bullets(prose, opts, make):
    words = sum(len(pack_util.words(masked)) for _ln, _off, _raw, masked in prose)
    if words > opts["max_short_note_words"]:
        return []
    hits = [(ln, off, raw, m) for ln, off, raw, masked in prose
            if (m := _BULLET_LINE.match(masked))]
    if len(hits) < opts["min_bullets"]:
        return []
    ln, off, raw, m = hits[0]
    label = (f"{len(hits)} list items in a {words}-word personal note; "
             "write plain sentences instead of a bulleted spec")
    return [make(ln, off, "bulleted_personal_email", label,
                 m.start(), m.end(), raw, raw.strip()[:100])]


def _scan_metric_parens(prose, opts, make):
    hits = []
    dense = []
    for ln, off, raw, masked in prose:
        for m in _PAREN.finditer(masked):
            inner = m.group(1)
            nums = _NUM_UNIT.findall(inner)
            if not nums:
                continue
            item = (ln, off, raw, m.start(), m.end(), len(nums))
            hits.append(item)
            if len(nums) >= 2 and ("," in inner or ";" in inner or "|" in inner):
                dense.append(item)
    out = []
    if dense:
        for ln, off, raw, s, e, count in dense:
            out.append(make(ln, off, "parenthetical_metric_stuffing",
                            f"dense parenthetical stat pack ({count} metrics); "
                            "state one plain fact or move numbers to a linked page",
                            s, e, raw, raw.strip()[:100]))
    elif len(hits) >= opts["min_metric_parens"]:
        ln, off, raw, s, e, _c = hits[0]
        out.append(make(ln, off, "parenthetical_metric_stuffing",
                        f"{len(hits)} parenthetical metric packs in a personal note; "
                        "drop the stat-dump parentheses",
                        s, e, raw, raw.strip()[:100]))
    return out


def scan(text, prose, opts, make):
    found = pack_util.empty()
    found["MEDIUM"] += _scan_bullets(prose, opts, make)
    found["MEDIUM"] += _match_all(
        prose, _STIFF_OPENER, "stiff_template_opener",
        "stiff template opener; start directly with the point", make)
    found["MEDIUM"] += _match_all(
        prose, _ENUM_CRUTCH, "enumeration_crutch",
        "formulaic enumeration setup; state the point directly", make)
    found["MEDIUM"] += _match_all(
        prose, _PR_CLOSER, "symmetrical_pr_closer",
        "canned PR closer; end plainly when the note is done", make)
    found["MEDIUM"] += _scan_metric_parens(prose, opts, make)
    return found


def fingerprint():
    return [
        _BULLET_LINE.pattern,
        _STIFF_OPENER.pattern,
        _ENUM_CRUTCH.pattern,
        _PR_CLOSER.pattern,
        _PAREN.pattern,
        _NUM_UNIT.pattern,
    ]

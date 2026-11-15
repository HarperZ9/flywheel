#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
articulate.pack_claims -- claims that point at their evidence (rule pack `claims`).

  claim-without-evidence (LOW)   a sentence makes a claim a reader would want
                                 to check (a superlative, a speed or accuracy
                                 figure, a guarantee, "proven", "secure",
                                 "works with", a statistic about people such
                                 as "90% of you", "studies show") and neither
                                 the rest of it nor the next sentence points
                                 at the thing itself: a link, a
                                 command or path in code, a number with its
                                 unit or count, a named test or file, a figure.

Each label carries the document's coverage: how many claim sentences the pack
found and how many of them point at evidence, so the share is always read with
its denominator. `coverage(text)` returns the same numbers for a report.

Two things limit the reading. The claim list is a closed set of the claim words
product copy leans on, so a claim phrased another way is not counted. And a
pointer is matched by its shape: a link that points at the wrong page still
counts as a pointer. The pack reports and never gates on its own; a domain
profile decides the tier. Standard library only.
"""
from __future__ import annotations

import re

from . import pack_util

NAME = "claims"
CATEGORIES = ("claim-without-evidence",)
OPTIONS = {"look_ahead": 1}

CLAIM = re.compile(
    r"(?i)\b(?:fastest|best-in-class|the best|(?:the|our) (?:first|only) (?:\w+ ){0,2}"
    r"(?:tool|library|system|platform|checker|product|service|way|one) (?:to|that|which)|"
    r"(?:the|a) leading|most (?:accurate|reliable|secure|complete)|"
    r"\d+(?:\.\d+)?\s*(?:x|times)\s+(?:faster|smaller|cheaper|better)|"
    r"(?:faster|more accurate|more reliable|cheaper) than|guarantees? (?:that|you|your|zero|100)|"
    r"proven to|provably|(?:is|are|fully) secure|secure by default|bulletproof|"
    r"zero[- ](?:bugs|false positives|errors)|never (?:fails|breaks|misses|loses)|"
    r"always (?:works|catches|finds)|100\s*% (?:accurate|reliable|secure|of)|"
    r"works (?:with|on|in) (?:any|every|all)|state[- ]of[- ]the[- ]art|enterprise[- ]ready|"
    r"production[- ]ready|battle[- ]tested|industry[- ]standard|"
    r"\d+(?:\.\d+)?\s*%\s+of (?:you|people|users|developers|readers|everyone|us)|"
    r"studies (?:show|prove)|research (?:shows|proves)|science says|everyone knows)\b")

EVIDENCE = re.compile(
    r"https?://|\]\(|`[^`]+`|\b[\w./-]+\.(?:py|md|json|jsonl|txt|csv|html|yml|yaml|toml|png|svg)\b|"
    r"\b(?:tests?|bench|benchmarks?|results?|receipts?|figure|table|appendix)/|"
    r"\b(?:see|measured|in|on|across|over|of)\s+(?:\d[\d,]*)\s+\w+|"
    r"\b\d[\d,.]*\s*(?:ms|s|seconds|minutes|%|percent|MB|GB|files|texts|runs|tests|pages)\b|"
    r"\b(?:Figure|Table|Fig\.)\s*\d|\[\d+\]")


def _sentences_with_raw(prose):
    """pack_util sentences, each with the raw text of its paragraph lines joined."""
    sents = pack_util.sentences(prose)
    raw_by_line = {rec[0]: rec[2] for rec in prose}
    for i, s in enumerate(sents):
        last = sents[i + 1]["line"] if i + 1 < len(sents) else s["line"]
        s["raw_text"] = " ".join(raw_by_line.get(n, "") for n in range(s["line"], last + 1))
    return sents


def _bound(sents, i, ahead, claim=""):
    """True when the claim sentence or the next points at evidence. The claim's own
    words are taken out first, so "90% of you" is not its own source."""
    for j in range(i, min(len(sents), i + 1 + ahead)):
        raw, text = sents[j]["raw_text"], sents[j]["text"]
        if j == i and claim:
            raw, text = raw.replace(claim, " "), text.replace(claim, " ")
        if EVIDENCE.search(raw) or EVIDENCE.search(text):
            return True
    return False


def _claims(prose, ahead):
    sents = _sentences_with_raw(prose)
    out = []
    for i, s in enumerate(sents):
        m = CLAIM.search(s["text"])
        if m:
            out.append((s, m, _bound(sents, i, ahead, m.group(0))))
    return out


def scan(text, prose, opts, make):
    found = pack_util.empty()
    claims = _claims(prose, opts["look_ahead"])
    bound = sum(1 for _s, _m, b in claims if b)
    for s, m, b in claims:
        if b:
            continue
        label = (f"claim {m.group(0)!r} points at no evidence in this or the next sentence; "
                 f"{bound} of {len(claims)} claim sentences here point at evidence")
        found["LOW"].append(pack_util.finding(make, s, "claim-without-evidence", label))
    return found


def coverage(text, look_ahead=1):
    """{'claims', 'bound', 'unbound_lines', 'scope'} for one document."""
    from . import rules_ext
    prose = list(rules_ext.prose_lines(text.splitlines(keepends=True)))
    claims = _claims(prose, look_ahead)
    return {"claims": len(claims), "bound": sum(1 for c in claims if c[2]),
            "unbound_lines": [c[0]["line"] for c in claims if not c[2]],
            "scope": "Counts claim sentences from a closed word list and the ones that point "
                     "at a link, code, a file, a figure or a counted number."}


def fingerprint():
    return [CLAIM.pattern, EVIDENCE.pattern]

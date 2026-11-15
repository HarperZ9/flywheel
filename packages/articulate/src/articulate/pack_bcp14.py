#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
articulate.pack_bcp14 -- RFC 2119 / RFC 8174 keyword consistency, run by the
`rfc-keywords` domain profile (the `normative-spec` register plus this pack).
The `normative-spec` profile itself is unchanged and runs no pack.

BCP 14 is RFC 2119 as updated by RFC 8174. Its eleven keywords are MUST, MUST
NOT, REQUIRED, SHALL, SHALL NOT, SHOULD, SHOULD NOT, RECOMMENDED, NOT
RECOMMENDED, MAY, and OPTIONAL. Under RFC 8174 they carry their special meaning
only in all capitals, and a document that uses them should say so with the
boilerplate sentence that cites BCP 14.

  bcp14-mixed-case (HIGH)    a keyword phrase in mixed case: "MUST not",
                             "SHOULD not", "must NOT", "NOT recommended". Its
                             force is ambiguous, so it gates.
  bcp14-no-boilerplate (MEDIUM)  capital keywords in a document that never cites
                             BCP 14, RFC 2119, or RFC 8174.
  bcp14-may-not (MEDIUM)     "MAY NOT", which neither RFC defines. Write MUST NOT
                             for a prohibition, or say the step is not required.
  bcp14-lowercase (LOW)      a lowercase "must", "shall", or "should" in a
                             document that declares BCP 14. Under RFC 8174 it has
                             its plain English sense; write it in capitals if a
                             requirement is meant. Lowercase "may", "required",
                             "recommended", and "optional" are left alone, since
                             they are common plain words.
  bcp14-shall-must (LOW)     both SHALL and MUST in one document. RFC 2119 makes
                             them synonyms, so the mix reads as two strengths.
  bcp14-old-boilerplate (LOW)  a declaration that cites RFC 2119 without the RFC
                             8174 clause "when, and only when, they appear in all
                             capitals".

English only. Standard library only.
"""
from __future__ import annotations

import re

from . import pack_util

NAME = "bcp14"
CATEGORIES = ("bcp14-mixed-case", "bcp14-no-boilerplate", "bcp14-may-not",
              "bcp14-lowercase", "bcp14-shall-must", "bcp14-old-boilerplate")
OPTIONS = {}

_DECLARED = re.compile(r"\b(?:BCP\s?14|RFC\s?2119|RFC\s?8174)\b")
_RFC8174_CLAUSE = re.compile(r"(?i)when,?\s+and\s+only\s+when,?\s+they\s+appear\s+in\s+all\s+capitals")
_UPPER = re.compile(r"\b(?:NOT RECOMMENDED|MUST NOT|SHALL NOT|SHOULD NOT|MUST|SHALL|SHOULD"
                    r"|REQUIRED|RECOMMENDED|MAY|OPTIONAL)\b")
_MIXED = re.compile(r"\b(?:(?:MUST|SHALL|SHOULD)\s+not|(?:[Mm]ust|[Ss]hall|[Ss]hould)\s+NOT"
                    r"|NOT\s+recommended|[Nn]ot\s+RECOMMENDED)\b")
_MAY_NOT = re.compile(r"\bMAY\s+NOT\b")
_LOWER = re.compile(r"\b(?:must|shall|should)\b")


def _prose_hits(prose, rx, line_filter=None):
    """(line_no, off, raw, match) for each match in the masked prose, skipping
    quoted keywords such as the boilerplate's own "MUST"."""
    for line_no, off, raw, masked in prose:
        if line_filter and not line_filter(masked):
            continue
        for m in rx.finditer(masked):
            before, after = masked[m.start() - 1:m.start()], masked[m.end():m.end() + 1]
            if before in ("\"", "“") and after in ("\"", "”"):
                continue
            yield line_no, off, raw, m


def _add(found, tier, make, hit, cat, label):
    line_no, off, raw, m = hit
    found[tier].append(make(line_no, off, cat, label, m.start(), m.end(), raw,
                            raw.strip()[:100]))


def _declaration_checks(prose, masked_text, found, make):
    declared = bool(_DECLARED.search(masked_text))
    upper = list(_prose_hits(prose, _UPPER))
    if upper and not declared:
        _add(found, "MEDIUM", make, upper[0], "bcp14-no-boilerplate",
             "BCP 14 keywords with no boilerplate citing BCP 14 (RFC 2119, RFC 8174)")
    if declared and not _RFC8174_CLAUSE.search(masked_text):
        hit = next(_prose_hits(prose, _DECLARED), None)
        if hit:
            _add(found, "LOW", make, hit, "bcp14-old-boilerplate",
                 "the declaration lacks the RFC 8174 clause 'when, and only when, they "
                 "appear in all capitals'")
    return declared, upper


def scan(text, prose, opts, make):
    found = pack_util.empty()
    masked_text = "\n".join(rec[3] for rec in prose)
    declared, upper = _declaration_checks(prose, masked_text, found, make)
    for hit in _prose_hits(prose, _MIXED):
        _add(found, "HIGH", make, hit, "bcp14-mixed-case",
             f"BCP 14 keyword in mixed case: {hit[3].group(0)!r}; write it all in capitals")
    for hit in _prose_hits(prose, _MAY_NOT):
        _add(found, "MEDIUM", make, hit, "bcp14-may-not",
             "MAY NOT is not a BCP 14 keyword; write MUST NOT, or say it is not required")
    if declared:
        for hit in _prose_hits(prose, _LOWER):
            _add(found, "LOW", make, hit, "bcp14-lowercase",
                 f"lowercase {hit[3].group(0)!r} has no BCP 14 force; use capitals "
                 f"if a requirement is meant")
    words = [h[3].group(0).split()[0] for h in upper]
    if "SHALL" in words and "MUST" in words:
        minority = "SHALL" if words.count("SHALL") <= words.count("MUST") else "MUST"
        hit = next(h for h in upper if h[3].group(0).startswith(minority))
        _add(found, "LOW", make, hit, "bcp14-shall-must",
             "both SHALL and MUST appear; pick one for requirements")
    return found


def fingerprint():
    return [rx.pattern for rx in (_DECLARED, _RFC8174_CLAUSE, _UPPER, _MIXED, _MAY_NOT, _LOWER)]

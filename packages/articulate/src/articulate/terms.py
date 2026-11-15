#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
articulate.terms -- project terminology rules from the project config.

Two rule kinds, each with its own rule ids so a finding says which project rule
fired:

  banned     a term the project does not use, with a reason and an optional
             suggestion. Rule id `terminology/banned/<term>`. HIGH by default,
             so it gates under a flavored or strict profile.
  preferred  a preferred form and the variants it replaces. Rule id
             `terminology/preferred/<preferred form>`. MEDIUM by default, so it
             gates under a strict profile and reports under a flavored one.

Each entry may set "severity" (high, medium, low) and "match_case". Matching is
whole-phrase, with any run of whitespace between words, and skips code, URLs,
markup, and fenced blocks. `allowed` terms are handled by the project module,
which adds them to the profile's terms-of-art keep list. Standard library only.
"""
from __future__ import annotations

import re

SEVERITIES = {"high": "HIGH", "medium": "MEDIUM", "low": "LOW"}
_KEYS = {"preferred": {"use", "instead_of", "reason", "severity", "match_case"},
         "banned": {"term", "reason", "suggestion", "severity", "match_case"}}


def _slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:48] or "term"


def _check_entry(kind, i, entry):
    where = f"{kind}[{i}]"
    if not isinstance(entry, dict):
        raise ValueError(f"{where} must be an object")
    bad = set(entry) - _KEYS[kind]
    if bad:
        raise ValueError(f"{where}: unknown {sorted(bad)}; known: {sorted(_KEYS[kind])}")
    head = "use" if kind == "preferred" else "term"
    if not isinstance(entry.get(head), str) or not entry[head].strip():
        raise ValueError(f"{where}: '{head}' must be a non-empty string")
    if kind == "preferred":
        alts = entry.get("instead_of")
        if not isinstance(alts, list) or not alts or \
                not all(isinstance(a, str) and a.strip() for a in alts):
            raise ValueError(f"{where}: 'instead_of' must be a non-empty list of strings")
    for key in ("reason", "suggestion"):
        if key in entry and not isinstance(entry[key], str):
            raise ValueError(f"{where}: '{key}' must be a string")
    if entry.get("severity", "high" if kind == "banned" else "medium") not in SEVERITIES:
        raise ValueError(f"{where}: 'severity' must be one of {sorted(SEVERITIES)}")
    if not isinstance(entry.get("match_case", False), bool):
        raise ValueError(f"{where}: 'match_case' must be true or false")


def validate(term):
    """Raise ValueError on a malformed terminology block."""
    if not isinstance(term, dict):
        raise ValueError("must be an object")
    bad = set(term) - {"preferred", "banned", "allowed"}
    if bad:
        raise ValueError(f"unknown {sorted(bad)}; known: allowed, banned, preferred")
    for kind in ("preferred", "banned"):
        entries = term.get(kind, [])
        if not isinstance(entries, list):
            raise ValueError(f"'{kind}' must be a list")
        for i, entry in enumerate(entries):
            _check_entry(kind, i, entry)
    allowed = term.get("allowed", [])
    if not isinstance(allowed, list) or not all(isinstance(a, str) and a.strip() for a in allowed):
        raise ValueError("'allowed' must be a list of non-empty strings")
    flagged = {b["term"].lower() for b in term.get("banned", [])}
    flagged |= {a.lower() for p in term.get("preferred", []) for a in p["instead_of"]}
    clash = flagged & {a.lower() for a in allowed}
    if clash:
        raise ValueError(f"{sorted(clash)} are both flagged and allowed")


def _rx(phrase, match_case):
    body = r"\s+".join(re.escape(w) for w in phrase.split())
    return re.compile(r"(?<![\w-])" + body + r"(?![\w-])", 0 if match_case else re.I)


def _label(head, reason, suggestion):
    text = head
    if suggestion:
        text += f"; suggestion: {suggestion!r}"
    if reason:
        text += f" ({reason})"
    return text


def rules(term):
    """(tier, rule_id, label, regex) for every terminology rule."""
    out = []
    for b in term.get("banned", []):
        tier = SEVERITIES[b.get("severity", "high")]
        label = _label(f"banned term {b['term']!r}", b.get("reason"), b.get("suggestion"))
        out.append((tier, f"terminology/banned/{_slug(b['term'])}", label,
                    _rx(b["term"], b.get("match_case", False))))
    for p in term.get("preferred", []):
        tier = SEVERITIES[p.get("severity", "medium")]
        for alt in p["instead_of"]:
            label = _label(f"preferred term {p['use']!r} for {alt!r}", p.get("reason"),
                           p["use"])
            out.append((tier, f"terminology/preferred/{_slug(p['use'])}", label,
                        _rx(alt, p.get("match_case", False))))
    return out


def scan(prose, term, make):
    """Findings by tier for the prose lines. `prose` yields (line_no, offset, raw,
    masked); `make` builds a finding record (the detector's span constructor)."""
    found = {"HIGH": [], "MEDIUM": [], "LOW": []}
    compiled = rules(term)
    for line_no, off, raw, masked in prose:
        for tier, rule_id, label, rx in compiled:
            for m in rx.finditer(masked):
                f = make(line_no, off, "terminology", label, m.start(), m.end(), raw,
                         raw.strip()[:100])
                f["rule_id"] = rule_id
                found[tier].append(f)
    return found

"""Scan, redact and report with the redaction catalog (7.7, I10).

Redaction applies where content leaves custody: an export, or a derivation
that sends content to a model. The owner's own copy is stored as it arrived.

Every hit becomes `[REDACTED:<rule_id>:<tag>]`, where the tag is the first
eight hex characters of an HMAC of the matched text under a key the caller
passes. One key gives one secret one tag, so a reader sees that two
redactions were the same value; a fresh key per export keeps two exports from
being linked through their tags. Reports carry counts per rule and never the
matched text.

Long strings are scanned in 64 KiB windows that overlap by 8 KiB, the
longest bounded token; a hit that runs into a window's end is extended to
the next whitespace. A per-call time budget is checked between windows and
rules and stops the scan with SCAN_BUDGET_EXCEEDED.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import re
import string
import time

from .trace_redact_rules import CATALOG_VERSION, INDEX, RULES, credential_rules, enabled

WINDOW = 64 * 1024
OVERLAP = 8 * 1024
TAIL_REGION = 12 * 1024
_MIB = 1 << 20
_NONSPACE = re.compile(r"\S{0,65536}")
# Only A to Z change, so every offset in the copy is the offset in the text.
_ASCII_LOWER = str.maketrans(string.ascii_uppercase, string.ascii_lowercase)
_PLACEHOLDER = re.compile(r"\[REDACTED:([a-z0-9_]+):([0-9a-f]{8})\]")

__all__ = ["CATALOG_VERSION", "Hit", "ScanBudgetExceeded", "WINDOW", "first_credential_rule",
           "placeholder", "placeholder_tags", "redact_line", "redact_lines", "redact_text",
           "scan"]


class ScanBudgetExceeded(RuntimeError):
    code = "SCAN_BUDGET_EXCEEDED"

    def __init__(self) -> None:
        super().__init__(self.code)


@dataclass(frozen=True)
class Hit:
    rule_id: str
    start: int
    end: int


def check_key(key) -> bytes:
    if type(key) is not bytes or len(key) < 16:
        raise ValueError("REDACTION_KEY_INVALID")
    return key


def deadline_for(text: str, rules, budget_s=None) -> float:
    if budget_s is None:
        budget_s = 1.0 + 0.05 * (len(text) / _MIB) * max(1, len(rules))
    return time.monotonic() + budget_s


def _regex_hits(rule, pattern, index, subject, text, pos, endpos, out):
    """Hits of one pattern in one window. `subject` is `text` or its
    lowercased copy; offsets are the same in both."""
    groups, validator, append = rule.group, rule.validator, out.append
    for match in pattern.finditer(subject, pos, endpos):
        for group in groups:
            start, end = match.span(group)
            if start >= 0:
                break
        else:
            continue
        if validator is not None and not validator(text[start:end]):
            continue
        if end == endpos < len(text):
            end = _NONSPACE.match(text, end).end()
        append((index, start, end))


def _windows(rule, pattern, index, subject, text, out, deadline):
    pos, size = 0, len(text)
    while True:
        endpos = min(size, pos + WINDOW)
        _regex_hits(rule, pattern, index, subject, text, pos, endpos, out)
        if time.monotonic() > deadline:
            raise ScanBudgetExceeded()
        if endpos >= size:
            return
        pos = endpos - OVERLAP


def _tail_hits(rule, index, text, out):
    match = rule.tail.search(text, max(0, len(text) - TAIL_REGION))
    if match is not None and (rule.validator is None or rule.validator(match.group(0))):
        out.append((index, match.start(), match.end()))


def raw_hits(text: str, rules, deadline: float) -> list[tuple[int, int, int]]:
    """Unmerged (rule index, start, end) hits of `rules` in `text`."""
    out: list[tuple[int, int, int]] = []
    lowered = None
    for rule in rules:
        index = INDEX.get(rule.id, len(INDEX))
        if rule.finder is not None:
            out.extend((index, s, e) for s, e in rule.finder(text))
        subject = text
        if rule.lower:
            lowered = lowered if lowered is not None else text.translate(_ASCII_LOWER)
            subject = lowered
        for pattern in rule.patterns:
            _windows(rule, pattern, index, subject, text, out, deadline)
        if rule.tail is not None:
            _tail_hits(rule, index, text, out)
        if time.monotonic() > deadline:
            raise ScanBudgetExceeded()
    return out


def merge(hits, rules) -> list[Hit]:
    """Overlapping spans become one span; it counts once, for the rule that
    comes first in the catalog."""
    ids = {INDEX.get(r.id, len(INDEX)): r.id for r in rules}
    merged: list[list[int]] = []
    for index, start, end in sorted(hits, key=lambda h: (h[1], h[0])):
        if merged and start < merged[-1][2]:
            merged[-1][2] = max(merged[-1][2], end)
            merged[-1][0] = min(merged[-1][0], index)
        else:
            merged.append([index, start, end])
    return [Hit(ids[i], s, e) for i, s, e in merged]


def scan(text: str, *, rules_=None, personal: bool = False, enable=(),
         budget_s=None, deadline=None) -> list[Hit]:
    rules = tuple(rules_) if rules_ is not None else enabled(personal=personal, enable=enable)
    limit = deadline if deadline is not None else deadline_for(text, rules, budget_s)
    return merge(raw_hits(text, rules, limit), rules)


def placeholder(rule_id: str, matched: str, key: bytes) -> str:
    tag = hmac.new(key, matched.encode("utf-8", "surrogatepass"), hashlib.sha256).hexdigest()
    return f"[REDACTED:{rule_id}:{tag[:8]}]"


def apply(text: str, hits, key: bytes) -> tuple[str, dict]:
    parts, last, counts = [], 0, {}
    for hit in hits:
        parts += [text[last:hit.start], placeholder(hit.rule_id, text[hit.start:hit.end], key)]
        last = hit.end
        counts[hit.rule_id] = counts.get(hit.rule_id, 0) + 1
    parts.append(text[last:])
    return "".join(parts), counts


def redact_text(text: str, *, key: bytes, rules_=None, personal=False, enable=(),
                deadline=None) -> tuple[str, dict]:
    hits = scan(text, rules_=rules_, personal=personal, enable=enable, deadline=deadline)
    return apply(text, hits, check_key(key))


def redact_line(line: str, *, key: bytes, personal: bool = False, enable=()) -> tuple[str, dict]:
    """Redact one transcript line: decoded JSON when it parses, else raw and
    unescaped text. A line with no hit is returned byte for byte."""
    from .trace_redact_json import redact_json_line
    rules = enabled(personal=personal, enable=enable)
    return redact_json_line(line, key=check_key(key), rules=rules,
                            deadline=deadline_for(line, rules))


def redact_lines(lines, *, key: bytes, personal: bool = False, enable=()) -> tuple[list, dict]:
    out, counts, affected = [], {}, 0
    for line in lines:
        new, found = redact_line(line, key=key, personal=personal, enable=enable)
        out.append(new)
        affected += bool(found)
        for rule_id, n in found.items():
            counts[rule_id] = counts.get(rule_id, 0) + n
    return out, {"catalog_version": CATALOG_VERSION, "counts": counts,
                 "lines_affected": affected, "lines_scanned": len(out),
                 "mode": {"credentials": True, "personal": personal,
                          "enabled": sorted(enable)}}


def placeholder_tags(text: str) -> list[str]:
    return [m.group(2) for m in _PLACEHOLDER.finditer(text)]


def first_credential_rule(value) -> str:
    """The guard classifier: which credential rule a refused value hits, in
    memory only. Personal rules never classify a refusal."""
    from .trace_redact_json import first_hit
    try:
        return first_hit(value, credential_rules()) or "unclassified"
    except ScanBudgetExceeded:
        return ScanBudgetExceeded.code


RULE_IDS = tuple(r.id for r in RULES)

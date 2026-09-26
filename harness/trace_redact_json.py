"""Decoded matching for transcript lines (7.7, SP-26).

A secret in a JSON line can hide behind escapes (`\\n` inside a PEM block,
`\\u0067` for a letter) or inside a string that is itself JSON. So the line is
parsed and every decoded string value is scanned; a string that parses as a
JSON object or array is walked in turn, up to four levels. A value under a
credential-named key is redacted whole. Redacted values are written back and
the line is re-serialized; a line with no hit comes back unchanged.

A line that does not parse is scanned twice, as raw text and as an unescaped
view with the JSON escapes decoded, and each hit in the view is mapped back
to the raw bytes it came from.
"""
from __future__ import annotations

from bisect import bisect_right
import json
import re

from .trace_redact import apply, merge, raw_hits

MAX_NESTED = 4
_SECRET_KEY = re.compile(
    r"(?i)(?:[A-Za-z0-9_\-]{0,64}[_\-])?(?:password|passwd|pwd|secret|token|api[_\-]?key|"
    r"access[_\-]?key|private[_\-]?key|client[_\-]?secret|credentials?|authorization|"
    r"cookie|set[_\-]cookie|auth[_\-]?token|refresh[_\-]?token|access[_\-]?token)s?\Z")
_B64 = re.compile(r"[A-Za-z0-9+/]{8,4096}={0,2}\Z")
_ESC = re.compile(r'\\(?:u([0-9a-fA-F]{4})|(["\\/bfnrt]))')
_SIMPLE = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r",
           "t": "\t"}


def key_rule(name, value) -> str | None:
    """The rule a whole value falls under because of the key that holds it."""
    if type(value) is not str or len(value) < 8 or type(name) is not str:
        return None
    if name == "auth" and _B64.match(value):
        return "docker_auth"
    return "credential_assignment" if _SECRET_KEY.match(name) else None


def _parse_nested(text: str, level: int):
    if level >= MAX_NESTED or text.lstrip()[:1] not in ("{", "["):
        return None
    try:
        value = json.loads(text)
    except (ValueError, RecursionError):
        return None
    return value if type(value) in (dict, list) else None


class _Redactor:
    def __init__(self, key, rules, deadline):
        self.key, self.rules, self.deadline, self.counts = key, rules, deadline, {}
        self.allowed = {r.id for r in rules}

    def walk(self, value, level):
        if type(value) is dict:
            out = {}
            for name, child in value.items():
                rule_id = key_rule(name, child)
                out[name] = (self.redact_whole(rule_id, child) if rule_id in self.allowed
                             else self.walk(child, level))
            return out
        if type(value) is list:
            return [self.walk(child, level) for child in value]
        if type(value) is str:
            return self.string(value, level)
        return value

    def redact_whole(self, rule_id, value):
        from .trace_redact import placeholder
        self.counts[rule_id] = self.counts.get(rule_id, 0) + 1
        return placeholder(rule_id, value, self.key)

    def string(self, text, level):
        nested = _parse_nested(text, level)
        if nested is not None:
            before = sum(self.counts.values())
            walked = self.walk(nested, level + 1)
            return json.dumps(walked, ensure_ascii=False) if sum(
                self.counts.values()) != before else text
        hits = merge(raw_hits(text, self.rules, self.deadline), self.rules)
        redacted, found = apply(text, hits, self.key)
        for rule_id, n in found.items():
            self.counts[rule_id] = self.counts.get(rule_id, 0) + n
        return redacted


def redact_json_line(line: str, *, key: bytes, rules, deadline) -> tuple[str, dict]:
    try:
        value = json.loads(line)
    except (ValueError, RecursionError):
        return _redact_raw(line, key, rules, deadline)
    redactor = _Redactor(key, rules, deadline)
    walked = redactor.walk(value, 0)
    if not redactor.counts:
        return line, {}
    return json.dumps(walked, ensure_ascii=False), redactor.counts


def unescaped_view(raw: str):
    """The text with JSON escapes decoded, and segments mapping it back."""
    parts, segments, view_pos, pos = [], [], 0, 0
    for match in _ESC.finditer(raw):
        if match.start() > pos:
            literal = raw[pos:match.start()]
            parts.append(literal)
            segments.append((view_pos, pos, len(literal), True))
            view_pos += len(literal)
        code, simple = match.group(1), match.group(2)
        parts.append(chr(int(code, 16)) if code else _SIMPLE[simple])
        segments.append((view_pos, match.start(), match.end() - match.start(), False))
        view_pos, pos = view_pos + 1, match.end()
    if pos < len(raw):
        parts.append(raw[pos:])
        segments.append((view_pos, pos, len(raw) - pos, True))
    return "".join(parts), segments


def _to_raw(segments, starts, index, *, end):
    view_start, raw_start, raw_len, literal = segments[bisect_right(starts, index) - 1]
    if literal:
        return raw_start + (index - view_start) + (1 if end else 0)
    return raw_start + (raw_len if end else 0)


def _redact_raw(line, key, rules, deadline):
    hits = raw_hits(line, rules, deadline)
    view, segments = unescaped_view(line)
    if segments and view != line:
        starts = [s[0] for s in segments]
        for index, start, end in raw_hits(view, rules, deadline):
            hits.append((index, _to_raw(segments, starts, start, end=False),
                         _to_raw(segments, starts, end - 1, end=True)))
    return apply(line, merge(hits, rules), key)


def first_hit(value, rules, level: int = 0) -> str | None:
    """The first credential rule a value hits, walking keys, strings and
    nested JSON the same way redaction does. Nothing is written anywhere."""
    from .trace_redact import deadline_for, scan
    allowed = {r.id for r in rules}
    if type(value) is dict:
        for name, child in value.items():
            rule_id = key_rule(name, child)
            found = rule_id if rule_id in allowed else first_hit(child, rules, level)
            if found:
                return found
    elif type(value) is list:
        for child in value:
            found = first_hit(child, rules, level)
            if found:
                return found
    elif type(value) is str:
        nested = _parse_nested(value, level)
        if nested is not None:
            return first_hit(nested, rules, level + 1)
        hits = scan(value, rules_=rules, deadline=deadline_for(value, rules))
        return hits[0].rule_id if hits else None
    return None

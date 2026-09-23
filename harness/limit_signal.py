"""limit_signal.py -- read output for a limit error that exited 0.

A command, a hook or a CLI session can finish with exit code 0 while its
output says the account hit a rate limit, ran out of quota, owes money, failed
to sign in or found the service overloaded. Anything that trusts the exit code
alone records that as success, and a scheduler or retry loop keeps paying for
it. This module names the kind of limit an output reports and says how much
the match can be trusted.

Three kinds of evidence are read, and they are not trusted equally:

- structured: an HTTP status line (`HTTP/2 429`), or a JSON status, code,
  type or reason field that names a limit (`"status": 429`,
  `"type": "billing_error"`). A tool prints these when a request came back
  that way.
- terminal: the words a provider or CLI prints when it stops on a limit
  ("usage limit reached", "insufficient_quota", "credit balance is too low",
  "please run /login").
- mention: the same limits as prose, test names, commit subjects and retry
  logs use them ("rate limited", "HTTP 429", "not logged in").

A match is anchored when it is structured, when a terminal phrase sits on the
output's last non-empty line, or when a mention opens that line or follows an
error prefix there ("Error: 429 Too Many Requests"). The last line is where a
CLI prints the error it stopped on, and a passing test log ends on its
summary instead. Callers act on anchored matches and only record the rest.

It is an English phrase heuristic and says so wherever its verdict is
recorded. It misses an error worded another way or written in another
language, and an anchored match can still be a quote. Standard library only,
so the hook runner and the scheduler can use it without importing the agent
worker.
"""
from __future__ import annotations

import re
from typing import NamedTuple

_STATUS = r"(?:status|http|error|code)[\s:=]*"
_CODE_KINDS = {"429": "rate_limit", "402": "billing", "401": "auth",
               "503": "overloaded", "529": "overloaded"}


def _compile(pairs) -> tuple:
    return tuple((name, re.compile(pattern, re.IGNORECASE)) for name, pattern in pairs)


_TERMINAL = _compile((
    ("rate_limit", r"\b(?:hit|reached) your (?!(?:[\w-]+ )?spend )(?:[\w-]+ ){0,2}limit\b"
                   r"|\b(?:usage|session|weekly|daily|\d+-hour) limit (?:reached|exceeded|hit)(?![a-z])"
                   r"|\brate[ _-]?limit[ _-]?reached(?![a-z])"),
    ("quota", r"\binsufficient[ _-]quota(?![a-z])|\bexceeded[ _](?:your[ _])?current[ _]quota(?![a-z])"
              r"|\bresource[ _-]exhausted(?![a-z])"),
    ("billing", r"\bcredit balance is too low\b|\bbilling[ _-]error(?![a-z])"
                r"|\b(?:hit|reached) your (?:[\w-]+ )?spend limit\b|\bspend limit reached\b"
                r"|\bbilling[ _-](?:hard[ _-])?limit(?![a-z])"
                r"|\bout of (?:extra )?usage(?: credits)?(?! [a-z])"),
    ("auth", r"\binvalid[ _-](?:x[ _-])?api[ _-]key\b|\bincorrect api key\b"
             r"|\bapi[ _-]?key[ _-](?:not[ _-]valid|invalid)(?![a-z])|\bplease run /login\b"
             r"|\bauthentication[ _-]error(?![a-z])"),
    ("overloaded", r"\boverloaded[ _-]error(?![a-z])"),
))
_MENTION = _compile((
    ("rate_limit", r"\brate[ _-]?limit(?:ed\b|[ _-]?(?:exceeded|error|hit)(?![a-z]))"
                   r"|\btoo many requests\b|\b" + _STATUS + r"429\b"),
    ("quota", r"\bquota[ _-](?:exceeded|exhausted|reached)(?![a-z])"),
    ("billing", r"\bpayment[ _-]required\b|\b" + _STATUS + r"402\b"),
    ("auth", r"\bauthentication[ _-]failed\b|\b" + _STATUS + r"401\b|\b401 unauthori[sz]ed\b"
             r"|\bnot logged in\b|\b(?:api key|token) (?:is |has )?(?:invalid|expired|revoked)\b"),
    ("overloaded", r"\b" + _STATUS + r"(?:503|529)\b"),
))
_STATUS_LINE = re.compile(r"(?m)^[ \t]*HTTP/\d(?:\.\d)?[ \t]+(\d{3})\b")
_JSON_NUMBER = re.compile(
    r'"(?:status|code|statusCode|status_code|http_status)"\s*:\s*"?(\d{3})\b', re.IGNORECASE)
_JSON_WORD = re.compile(r'"(?:type|code|status|reason|error)"\s*:\s*"([A-Za-z][A-Za-z_ ]{2,48})"')
# A line that opens with an error marker: "Error:", "API Error:", "npm ERR!".
_ERROR_LEAD = re.compile(
    r"^\W{0,3}(?:[\w.-]{1,32}[:\s]\s*)?(?:api\s+)?(?:error|fatal|err!?|failed)\b", re.IGNORECASE)
_LINE_LEAD = re.compile(r"^\W{0,3}(?:\d{3}\s+)?")

#: The pattern names, in order. A test holds them equal to
#: run_budget_contract.SIGNALS, the vocabulary the gateway accepts.
PATTERN_NAMES = tuple(name for name, _ in _TERMINAL)

#: How much output is read whole. Longer output is read at head and tail.
WHOLE_OUTPUT_CHARS = 2000
#: The longest excerpt kept. It is a span of the vocabulary above, never free text.
MATCH_CHARS = 80


class LimitMatch(NamedTuple):
    """One limit an output reports: its kind, the matched span and its tier."""
    kind: str
    match: str
    tier: str
    anchored: bool
    #: Offset of the match in the text it was found in (the line for an
    #: anchored phrase, the read window otherwise).
    start: int


def _word_kind(value: str) -> str | None:
    words = value.replace("_", " ")
    for patterns in (_TERMINAL, _MENTION):
        for name, pattern in patterns:
            if pattern.search(words):
                return name
    return None


def _structured(window: str) -> LimitMatch | None:
    for pattern in (_STATUS_LINE, _JSON_NUMBER):
        for m in pattern.finditer(window):
            kind = _CODE_KINDS.get(m.group(1))
            if kind is not None:
                return LimitMatch(kind, m.group(0).strip()[:MATCH_CHARS], "structured",
                                  True, m.start())
    for m in _JSON_WORD.finditer(window):
        kind = _word_kind(m.group(1))
        if kind is not None:
            return LimitMatch(kind, m.group(0)[:MATCH_CHARS], "structured", True, m.start())
    return None


def _last_line(body: str) -> str:
    line = body.splitlines()[-1].strip()
    return line if len(line) <= 600 else line[-600:]


def _opens_line(line: str, m) -> bool:
    return bool(_ERROR_LEAD.match(line)) or m.start() <= _LINE_LEAD.match(line).end()


def limit_match(text) -> LimitMatch | None:
    """The limit a piece of output reports, with the tier it was read at.

    Short output is read whole. Long output is read at its head and tail,
    where a CLI prints the error it stopped on, so a long log that quotes a
    phrase only in its middle does not read as a failure."""
    if type(text) is not str or not text.strip():
        return None
    body = text.strip()
    window = (body if len(body) <= WHOLE_OUTPUT_CHARS
              else body[:600] + "\n" + body[-900:])
    found = _structured(window)
    if found is not None:
        return found
    last = _last_line(body)
    for tier, patterns in (("terminal", _TERMINAL), ("mention", _MENTION)):
        for name, pattern in patterns:
            m = pattern.search(last)
            if m and (tier == "terminal" or _opens_line(last, m)):
                return LimitMatch(name, m.group(0)[:MATCH_CHARS], tier, True, m.start())
    for tier, patterns in (("terminal", _TERMINAL), ("mention", _MENTION)):
        for name, pattern in patterns:
            m = pattern.search(window)
            if m:
                return LimitMatch(name, m.group(0)[:MATCH_CHARS], tier, False, m.start())
    return None


def limit_signal(text) -> str | None:
    """The kind of limit a piece of output mentions at any tier, or None."""
    found = limit_match(text)
    return None if found is None else found.kind

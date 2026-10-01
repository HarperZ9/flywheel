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

A match carries a token from the fixed vocabulary in MATCH_TOKENS, such as
"usage limit reached" or "status 429", and never the text it was found in.
A word the pattern skips over, an account or a model name, cannot reach a
hook receipt or the card through it.

It is an English phrase heuristic and says so wherever its verdict is
recorded. It misses an error worded another way or written in another
language, and an anchored match can still be a quote.

`provider_limit` and `provider_body_limit` are the other half: they read a
limit from a provider's or a CLI's own fields (a status code, an error type)
by exact value, and read no free text at all. The text and provider-native
tool loops use only those. A CLI session reads its fields with them too, and
reads two texts with limit_match: the CLI's own stderr at the end of the
session, and the message of a Codex error event. Tool output and the answer
are read on no agent path; see docs/RUN-BUDGET.md. Standard library only, so
the hook runner and the scheduler can use this module without importing the
agent worker.
"""
from __future__ import annotations

import re
from typing import NamedTuple

_STATUS = r"(?:status|http|error|code)[\s:=]*"
_CODE_KINDS = {"429": "rate_limit", "402": "billing", "401": "auth",
               "503": "overloaded", "529": "overloaded"}


def _compile(rows) -> tuple:
    """One alternation per kind, one named group per token.

    A record carries the token of the alternative that matched, never the
    matched text, so a free word the pattern skips over (an account or model
    name) cannot reach a receipt or the card."""
    compiled = []
    for kind, alternatives in rows:
        tokens = tuple(token for token, _ in alternatives)
        pattern = "|".join(f"(?P<t{i}>{body})" for i, (_, body) in enumerate(alternatives))
        compiled.append((kind, tokens, re.compile(pattern, re.IGNORECASE)))
    return tuple(compiled)


def _token(tokens: tuple, m) -> str:
    return tokens[int(m.lastgroup[1:])]


_TERMINAL = _compile((
    ("rate_limit", (
        ("hit your limit", r"\b(?:hit|reached) your (?!(?:[\w-]+ )?spend )(?:[\w-]+ ){0,2}limit\b"),
        ("usage limit reached",
         r"\b(?:usage|session|weekly|daily|\d+-hour) limit (?:reached|exceeded|hit)(?![a-z])"),
        ("rate_limit_reached", r"\brate[ _-]?limit[ _-]?reached(?![a-z])"))),
    ("quota", (
        ("insufficient_quota", r"\binsufficient[ _-]quota(?![a-z])"),
        ("exceeded current quota", r"\bexceeded[ _](?:your[ _])?current[ _]quota(?![a-z])"),
        ("resource_exhausted", r"\bresource[ _-]exhausted(?![a-z])"))),
    ("billing", (
        ("credit balance is too low", r"\bcredit balance is too low\b"),
        ("billing_error", r"\bbilling[ _-]error(?![a-z])"),
        ("spend limit reached",
         r"\b(?:hit|reached) your (?:[\w-]+ )?spend limit\b|\bspend limit reached\b"),
        ("billing limit", r"\bbilling[ _-](?:hard[ _-])?limit(?![a-z])"),
        ("out of usage", r"\bout of (?:extra )?usage(?: credits)?(?! [a-z])"))),
    ("auth", (
        ("invalid api key", r"\binvalid[ _-](?:x[ _-])?api[ _-]key\b|\bincorrect api key\b"
                            r"|\bapi[ _-]?key[ _-](?:not[ _-]valid|invalid)(?![a-z])"),
        ("please run /login", r"\bplease run /login\b"),
        ("authentication_error", r"\bauthentication[ _-]error(?![a-z])"))),
    ("overloaded", (("overloaded_error", r"\boverloaded[ _-]error(?![a-z])"),)),
))
_MENTION = _compile((
    ("rate_limit", (
        ("rate limit", r"\brate[ _-]?limit(?:ed\b|[ _-]?(?:exceeded|error|hit)(?![a-z]))"),
        ("too many requests", r"\btoo many requests\b"),
        ("status 429", r"\b" + _STATUS + r"429\b"))),
    ("quota", (("quota exceeded", r"\bquota[ _-](?:exceeded|exhausted|reached)(?![a-z])"),)),
    ("billing", (
        ("payment required", r"\bpayment[ _-]required\b"),
        ("status 402", r"\b" + _STATUS + r"402\b"))),
    ("auth", (
        ("authentication failed", r"\bauthentication[ _-]failed\b"),
        ("status 401", r"\b" + _STATUS + r"401\b|\b401 unauthori[sz]ed\b"),
        ("not logged in", r"\bnot logged in\b"),
        ("credential invalid",
         r"\b(?:api key|token) (?:is |has )?(?:invalid|expired|revoked)\b"))),
    ("overloaded", (
        ("status 503", r"\b" + _STATUS + r"503\b"),
        ("status 529", r"\b" + _STATUS + r"529\b"))),
))
_STATUS_LINE = re.compile(r"(?m)^[ \t]*HTTP/\d(?:\.\d)?[ \t]+(\d{3})\b")
_JSON_NUMBER = re.compile(
    r'"(?:status|code|statusCode|status_code|http_status)"\s*:\s*"?(\d{3})\b', re.IGNORECASE)
_JSON_WORD = re.compile(r'"(?:type|code|status|reason|error)"\s*:\s*"([A-Za-z][A-Za-z_ ]{2,48})"')
# A line that opens with an error marker: "Error:", "API Error:", "npm ERR!".
_ERROR_LEAD = re.compile(
    r"^\W{0,3}(?:[\w.-]{1,32}[:\s]\s*)?(?:api\s+)?(?:error|fatal|err!?|failed)\b", re.IGNORECASE)
_LINE_LEAD = re.compile(r"^\W{0,3}(?:\d{3}\s+)?")

#: The kinds, in order. A test holds them equal to run_budget_contract.SIGNALS,
#: the vocabulary the gateway accepts.
PATTERN_NAMES = tuple(kind for kind, _, _ in _TERMINAL)

#: Error types a provider or a CLI puts in its own error fields, by kind.
#: Read by exact value only: a field that holds anything else is not a limit.
PROVIDER_ERROR_TYPES = {
    "rate_limit": "rate_limit", "rate_limit_error": "rate_limit",
    "rate_limit_exceeded": "rate_limit", "too_many_requests": "rate_limit",
    "insufficient_quota": "quota", "quota_exceeded": "quota",
    "resource_exhausted": "quota",
    "billing_error": "billing", "billing_hard_limit_reached": "billing",
    "payment_required": "billing",
    "authentication_error": "auth", "authentication_failed": "auth",
    "invalid_api_key": "auth", "unauthenticated": "auth",
    "overloaded_error": "overloaded", "overloaded": "overloaded",
    "service_unavailable": "overloaded"}

#: Every string a match can carry. A record holds one of these, never free text.
MATCH_TOKENS = frozenset(
    [token for _, tokens, _ in _TERMINAL + _MENTION for token in tokens]
    + [f"{lead} {code}" for code in _CODE_KINDS for lead in ("HTTP", "status")]
    + list(PROVIDER_ERROR_TYPES))

#: How much output is read whole. Longer output is read at head and tail.
WHOLE_OUTPUT_CHARS = 2000


class LimitMatch(NamedTuple):
    """One limit an output reports: its kind, the matched span and its tier."""
    kind: str
    match: str
    tier: str
    anchored: bool
    #: Offset of the match in the text it was found in (the line for an
    #: anchored phrase, the read window otherwise).
    start: int


def _word_match(value: str) -> tuple[str, str] | None:
    """The kind and token a JSON error word names, or None."""
    exact = PROVIDER_ERROR_TYPES.get(value.strip().lower().replace(" ", "_"))
    if exact is not None:
        return exact, value.strip().lower().replace(" ", "_")
    words = value.replace("_", " ")
    for patterns in (_TERMINAL, _MENTION):
        for kind, tokens, pattern in patterns:
            m = pattern.search(words)
            if m:
                return kind, _token(tokens, m)
    return None


def _structured(window: str) -> LimitMatch | None:
    for pattern, lead in ((_STATUS_LINE, "HTTP"), (_JSON_NUMBER, "status")):
        for m in pattern.finditer(window):
            kind = _CODE_KINDS.get(m.group(1))
            if kind is not None:
                return LimitMatch(kind, f"{lead} {m.group(1)}", "structured", True, m.start())
    for m in _JSON_WORD.finditer(window):
        found = _word_match(m.group(1))
        if found is not None:
            return LimitMatch(found[0], found[1], "structured", True, m.start())
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
    phrase only in its middle does not read as a failure. The match is a
    token from MATCH_TOKENS, never the text it was found in."""
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
        for kind, tokens, pattern in patterns:
            m = pattern.search(last)
            if m and (tier == "terminal" or _opens_line(last, m)):
                return LimitMatch(kind, _token(tokens, m), tier, True, m.start())
    for tier, patterns in (("terminal", _TERMINAL), ("mention", _MENTION)):
        for kind, tokens, pattern in patterns:
            m = pattern.search(window)
            if m:
                return LimitMatch(kind, _token(tokens, m), tier, False, m.start())
    return None


def limit_signal(text) -> str | None:
    """The kind of limit a piece of output mentions at any tier, or None."""
    found = limit_match(text)
    return None if found is None else found.kind


def provider_limit(*, status=None, error_type=None) -> LimitMatch | None:
    """A limit named by a provider's or a CLI's own fields, never by free text.

    `status` is an HTTP or API status code. `error_type` is an error type or
    code field, read by exact value against PROVIDER_ERROR_TYPES."""
    if type(error_type) is str:
        key = error_type.strip().lower().replace("-", "_").replace(" ", "_")
        if key in PROVIDER_ERROR_TYPES:
            return LimitMatch(PROVIDER_ERROR_TYPES[key], key, "structured", True, 0)
    if type(status) is int and str(status) in _CODE_KINDS:
        return LimitMatch(_CODE_KINDS[str(status)], f"status {status}", "structured", True, 0)
    return None


def provider_body_limit(body) -> LimitMatch | None:
    """A limit a provider response body names in its error object.

    Reads `error.type`, `error.code` and `error.status` (Anthropic, OpenAI and
    Gemini shapes) and nothing else: a message or detail string is free text."""
    error = body.get("error") if type(body) is dict else None
    if type(error) is not dict:
        return None
    for value in (error.get("type"), error.get("code"), error.get("status")):
        found = (provider_limit(error_type=value) if type(value) is str
                 else provider_limit(status=value))
        if found is not None:
            return found
    return None

"""scrub.py -- redact secret-shaped values before any text becomes a record.

A transcript holds whatever passed through the terminal: a pasted API key, a
bearer or basic auth header in a curl command, a cookie, a connection string
with its password, a `.env` or `~/.aws/credentials` line, a YAML `password:`
entry, a PGP key block. None of it may reach a record, a brief or an
instruction file. `scrub` replaces each match with `[REDACTED:<code>]` and
counts the hits by code; it never stores the value or a digest of it, since a
digest of a short password can be reversed by guessing.

Coverage is pattern-based and deliberately broad; the rules and their order are
in `scrub_rules.py`: provider key formats (Anthropic, OpenAI, GitHub, GitLab,
Slack, AWS, Google, Stripe, Hugging Face, npm, PyPI, DigitalOcean, Shopify,
SendGrid, Twilio, Telegram), JSON web tokens, private key blocks (PEM, PGP,
PuTTY), Slack and Discord webhook URLs, bearer, basic and API-key headers,
cookies, a URL query parameter whose name says key, token, secret, pass,
password, credential, auth, sig or code (its value ends at the next `&` or
`#`), Azure account keys, `.npmrc` tokens, JSON secret fields, password
fields in any case and after `=` or `:`, and assignments and command-line
flags (`--api-token=`) whose name says key, token, secret, pass, password or
credential, in any case. A value after such a name is judged by its shape
(`scrub_shape.py`): a number, a date, a path or a boolean is a setting, a
short word is a setting after a key or token name, and a name that qualifies
the secret word (`token_type`, `KEY_COUNT`) needs a value that looks random.

A URL's user part (`scheme://userinfo@host`) is redacted by one rule with two
cases. With a password (`user:password@`), the password is redacted whatever
it holds, unless it is a placeholder; a port followed by a path, a query, a
fragment or the end of the text is not a password. With no password, the
user part is redacted when it holds a run of eight or more letters and digits
that is not a word followed by a number (`scrub_shape.random_run`), read with
its percent escapes decoded. A user name such as `git@`, `deploy-bot-2024@`
or `GitHubUser42@` stays, and so do an email address and a placeholder such
as `${TOKEN}@`.

It does not prove a text is free of secrets; a secret with no recognisable
shape passes through. `find_secrets` is the same scan without the rewrite, used
as the last check before a store write and a render.
"""
from __future__ import annotations

import re
from bisect import bisect_left
from dataclasses import dataclass

from canon.workspace.scrub_rules import (
    _PLACEHOLDER,
    MARKER_RE,
    REDACTED,
    RULES,
    Check,
    beyond_markers,
)


@dataclass(frozen=True, slots=True)
class ScrubResult:
    text: str
    hits: dict[str, int]


class _Markers:
    """The earlier rules' markers in one text, read once per rule pass, so a
    text with many redactions is not re-scanned once per match."""

    def __init__(self, text: str) -> None:
        spans = [m.span() for m in MARKER_RE.finditer(text)]
        self.starts = [s for s, _ in spans]
        self.ends = [e for _, e in spans]

    def inside(self, pos: int) -> bool:
        i = bisect_left(self.starts, pos) - 1  # the last marker starting before pos
        return i >= 0 and pos < self.ends[i]

    def cut(self, start: int, end: int) -> bool:
        """True when the span starts or ends inside an earlier rule's marker,
        so a rule never re-reads the text of `[REDACTED:code]` as a secret."""
        return self.inside(start) or self.inside(end)


def _secret_span(match: re.Match[str], group: int, check: Check,
                 markers: _Markers) -> tuple[int, int] | None:
    value = match.group(group)
    if not value or markers.cut(*match.span(group)):
        return None
    if not beyond_markers(value):
        return None
    if check is not None:
        return match.span(group) if check(match, group) else None
    if group and _PLACEHOLDER.match(value.strip().strip("\"'")):
        return None
    return match.span(group)


def scrub(text: str) -> ScrubResult:
    """`text` with every secret-shaped value redacted, and the hit count per
    rule. Rules run in order, so a provider key is named by its provider before
    the generic assignment rule sees the line."""
    hits: dict[str, int] = {}
    for code, pattern, group, check in RULES:
        out: list[str] = []
        last = 0
        markers = _Markers(text)
        for match in pattern.finditer(text):
            span = _secret_span(match, group, check, markers)
            if span is None or span[0] < last:
                continue
            out.append(text[last:span[0]])
            out.append(REDACTED.format(code=code))
            last = span[1]
            hits[code] = hits.get(code, 0) + 1
        if out:
            out.append(text[last:])
            text = "".join(out)
    return ScrubResult(text, hits)


def find_secrets(text: str) -> list[str]:
    """The codes of every rule that still matches `text`, sorted."""
    found = set()
    markers = _Markers(text)
    for code, pattern, group, check in RULES:
        if any(_secret_span(m, group, check, markers) for m in pattern.finditer(text)):
            found.add(code)
    return sorted(found)


def secrets_in(value: object) -> list[str]:
    """`find_secrets` over every string inside a JSON-like value."""
    if isinstance(value, str):
        return find_secrets(value)
    items = value.values() if isinstance(value, dict) else value \
        if isinstance(value, list) else ()
    return sorted({code for item in items for code in secrets_in(item)})


def scrub_value(value: object, hits: dict[str, int]) -> object:
    """Scrub every string inside a JSON-like value, adding to `hits`."""
    if isinstance(value, str):
        result = scrub(value)
        merge_hits(hits, result.hits)
        return result.text
    if isinstance(value, list):
        return [scrub_value(item, hits) for item in value]
    if isinstance(value, dict):
        return {key: scrub_value(item, hits) for key, item in value.items()}
    return value


def merge_hits(into: dict[str, int], more: dict[str, int]) -> None:
    for code, count in more.items():
        into[code] = into.get(code, 0) + count

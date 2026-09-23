"""limit_signal.py -- read output for a limit error that exited 0.

A command, a hook or a CLI session can finish with exit code 0 while its
output says the account hit a rate limit, ran out of quota, owes money or
failed to sign in. Anything that trusts the exit code alone records that as
success, and a scheduler or retry loop keeps paying for it. This module
names the kind of limit an output reports, so the caller can record the step
as failed instead.

It is a phrase heuristic and says so wherever its verdict is recorded. It
misses an error worded another way, and it can flag a short output that
quotes one of the phrases. Standard library only, so the hook runner and the
scheduler can use it without importing the agent worker.
"""
from __future__ import annotations

import re

_STATUS = r"(?:status|http|error|code)[\s:=]*"
_PATTERNS = tuple((name, re.compile(pattern, re.IGNORECASE)) for name, pattern in (
    ("rate_limit", r"\brate[ _-]?limit(?:ed\b|[ _-]?(?:exceeded|reached|error|hit)\b)"
                   r"|\btoo many requests\b|\bhit your (?:usage |rate |session )?limit\b"
                   r"|\busage limit (?:reached|exceeded|hit)\b|\b" + _STATUS + r"429\b"),
    ("quota", r"\binsufficient[ _-]quota\b|\bquota (?:exceeded|exhausted|reached)\b"
              r"|\bexceeded your (?:current )?quota\b|\bresource[ _-]exhausted\b"),
    ("billing", r"\bcredit balance is too low\b|\bpayment required\b"
                r"|\bbilling[ _-](?:hard[ _-])?limit\b|\b" + _STATUS + r"402\b"),
    ("auth", r"\binvalid[ _-](?:x[ _-])?api[ _-]key\b|\bincorrect api key\b"
             r"|\bauthentication[ _-](?:error|failed)\b|\b" + _STATUS + r"401\b"
             r"|\b401 unauthori[sz]ed\b|\bplease run /login\b|\bnot logged in\b"
             r"|\b(?:api key|token) (?:is |has )?(?:invalid|expired|revoked)\b"),
    ("overloaded", r"\boverloaded[ _-]error\b|\b" + _STATUS + r"(?:503|529)\b"),
))
#: The pattern names, in order. A test holds them equal to
#: run_budget_contract.SIGNALS, the vocabulary the gateway accepts.
PATTERN_NAMES = tuple(name for name, _ in _PATTERNS)

#: How much output is read whole. Longer output is read at head and tail.
WHOLE_OUTPUT_CHARS = 2000


def limit_signal(text) -> str | None:
    """The kind of limit a piece of output reports, or None.

    Short output is read whole. Long output is read at its head and tail,
    where a CLI prints the error it stopped on, so a long log that quotes a
    phrase only in its middle does not read as a failure."""
    if type(text) is not str or not text.strip():
        return None
    body = text.strip()
    window = (body if len(body) <= WHOLE_OUTPUT_CHARS
              else body[:600] + "\n" + body[-900:])
    for name, pattern in _PATTERNS:
        if pattern.search(window):
            return name
    return None

"""model_deadlines.py -- when a provider says a call may be made again.

Split out of model_faults because it is a different problem. That module reads
WHAT went wrong. This one reads WHEN to come back, and the vendors answer that
question on two different clocks with headers that look alike:

- Anthropic's ``retry-after`` is a RELATIVE duration in seconds, documented as
  the number of seconds to wait, with earlier retries failing. Its
  ``anthropic-ratelimit-*-reset`` and ``anthropic-priority-*-reset`` family is
  an ABSOLUTE instant, documented as RFC 3339.
- OpenAI's ``Retry-After`` is a bare INTEGER count of seconds with a minimum of
  1, declared that way in the spec on both the rate-limited and the
  service-unavailable responses. Its ``x-ratelimit-reset-*`` family carries GO
  DURATION strings: ``1s``, ``3s``, ``6m0s``.

One parser across those families is the error this module exists to prevent. A
Go duration read by a bare integer parse turns ``6m0s`` into 6, so a client
waits six seconds for a limit that clears in three hundred and sixty and hits
the same wall on every attempt. An absolute instant read as a duration waits
until the heat death of the sun.

So a reading here carries its BASIS, and the two bases do not share a key. A
relative row has ``seconds`` and no ``epoch``. An absolute row has ``epoch``
and no ``seconds``. A caller reaching for the wrong one raises rather than
quietly computing a wrong wait.

Standard library only. This module never reads a clock and never makes a call.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from .model_dialects import ANTHROPIC, GEMINI, OLLAMA, OPENAI, OPENAI_RESPONSES

RELATIVE_SECONDS = "relative_seconds"
ABSOLUTE_INSTANT = "absolute_instant"

_ANTHROPIC_RESETS = ("anthropic-ratelimit-requests-reset",
                     "anthropic-ratelimit-tokens-reset",
                     "anthropic-ratelimit-input-tokens-reset",
                     "anthropic-ratelimit-output-tokens-reset",
                     "anthropic-priority-requests-reset",
                     "anthropic-priority-tokens-reset")
_OPENAI_RESETS = ("x-ratelimit-reset-requests", "x-ratelimit-reset-tokens",
                  "x-ratelimit-reset-project-requests",
                  "x-ratelimit-reset-project-tokens")


def _rows(names: tuple, basis: str, fmt: str) -> tuple:
    return tuple((name, basis, fmt) for name in names)


# Gemini and ollama are empty by decision rather than by oversight. The Gemini
# reference documents backoff through a RetryInfo entry inside error.details
# and this module has not read a spelling for it, so the fault record carries
# those details verbatim and no header is asserted here. ollama defines no
# timing header at all on either of its two envelopes.
DEADLINE_HEADERS = {
    ANTHROPIC: (_rows(("retry-after",), RELATIVE_SECONDS, "seconds")
                + _rows(_ANTHROPIC_RESETS, ABSOLUTE_INSTANT, "rfc3339")),
    OPENAI: (_rows(("retry-after",), RELATIVE_SECONDS, "seconds")
             + _rows(_OPENAI_RESETS, RELATIVE_SECONDS, "go_duration")),
    GEMINI: (),
    OLLAMA: (),
}
DEADLINE_HEADERS[OPENAI_RESPONSES] = DEADLINE_HEADERS[OPENAI]

_GO_UNITS = {"ns": 1e-9, "us": 1e-6, "µs": 1e-6, "μs": 1e-6,
             "ms": 1e-3, "s": 1.0, "m": 60.0, "h": 3600.0}
_GO_PART = re.compile(r"([0-9]*\.?[0-9]+)(ns|us|µs|μs|ms|s|m|h)")
_GO_WHOLE = re.compile(r"^-?(?:[0-9]*\.?[0-9]+(?:ns|us|µs|μs|ms|s|m|h))+$")


def go_duration(value: Any) -> "float | None":
    """Seconds from a Go duration string such as ``6m0s``, or None.

    A unitless number refuses. In an x-ratelimit-reset slot a bare value is not
    a Go duration, and reading it as seconds is the exact misread this parser
    exists to prevent.
    """
    if not isinstance(value, str) or not _GO_WHOLE.match(value.strip()):
        return None
    text = value.strip()
    total = sum(float(amount) * _GO_UNITS[unit]
                for amount, unit in _GO_PART.findall(text.lstrip("-")))
    return -total if text.startswith("-") else total


def seconds(value: Any) -> "float | None":
    """Seconds from a numeric Retry-After, or None.

    RFC 7231 also allows an HTTP-date in this header. Both vendors here
    document a count of seconds, so a date string refuses rather than being
    coerced, because a date read as a duration is a wait measured in decades.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if value >= 0 else None
    if not isinstance(value, str):
        return None
    try:
        parsed = float(value.strip())
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def rfc3339(value: Any) -> "float | None":
    """Epoch seconds from an RFC 3339 instant, or None.

    A string carrying no offset refuses. RFC 3339 requires one, and defaulting
    an offsetless string to UTC moves the instant by the reader's own timezone,
    which is a wrong answer wearing the shape of a right one.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        moment = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    return None if moment.tzinfo is None else moment.timestamp()


_PARSERS = {"seconds": seconds, "go_duration": go_duration, "rfc3339": rfc3339}


def read(headers: Any, *, dialect: str) -> list:
    """Every timing header this dialect defines, each carrying its basis.

    A list rather than a map keyed by meaning, because two headers can describe
    one limit on two clocks and collapsing them would force a choice this
    module has no grounds to make. A header present but unreadable is reported
    with ``read`` False and its verbatim value, so a spelling change shows up
    as an unread header rather than as a silently absent one.
    """
    out: list = []
    if not isinstance(headers, dict):
        return out
    lower = {k.lower(): v for k, v in headers.items() if isinstance(k, str)}
    for name, basis, fmt in DEADLINE_HEADERS.get(dialect, ()):
        if name not in lower:
            continue
        raw = lower[name]
        parsed = _PARSERS[fmt](raw)
        row = {"header": name, "basis": basis, "format": fmt,
               "verbatim": raw, "read": parsed is not None}
        if parsed is not None:
            row["seconds" if basis == RELATIVE_SECONDS else "epoch"] = parsed
        out.append(row)
    return out


def soonest(rows: Any) -> "dict | None":
    """The relative row with the shortest wait, or None if there is not one.

    Absolute rows are skipped rather than converted. Converting one needs a
    clock, this module does not read one, and a caller that has the current
    time can do the subtraction where the reading is used.
    """
    relative = [r for r in rows or ()
                if isinstance(r, dict) and "seconds" in r]
    return min(relative, key=lambda r: r["seconds"]) if relative else None


__all__ = ["ABSOLUTE_INSTANT", "DEADLINE_HEADERS", "RELATIVE_SECONDS",
           "go_duration", "read", "rfc3339", "seconds", "soonest"]

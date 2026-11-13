"""provider_retry_advice.py -- one plain sentence about trying again.

A fault record says ``retriable=True`` and lists a deadline row. Both are
correct and neither tells a person at a terminal what to do next. This module
turns the record into the sentence that does: whether sending the same request
again could help, and how long the provider asked the caller to wait first.

Nothing here retries, waits or reads a clock. The sentence says so, because a
line that names a wait and then returns reads as if something is waiting.

A relative wait is stated in seconds. An absolute reset instant is printed as
the UTC time the provider named and is never turned into a wait, since that
subtraction needs the current time and this module does not read it.

Standard library only.
"""
from __future__ import annotations

import datetime as _dt
from typing import Any

NO_AUTO_RETRY = "Flywheel does not retry on its own."

_UNCHANGED = {
    "auth": "the credential is replaced or corrected",
    "permission": "the credential is granted access",
    "quota": "the account's quota or billing changes",
    "too_large": "the request is made smaller",
    "not_found": "the model name or the address is corrected",
    "invalid_request": "the request is corrected",
}


def _seconds_text(value: Any) -> str:
    number = float(value)
    whole = int(number)
    amount = str(whole) if number == whole else f"{number:.1f}"
    return amount + (" second" if amount == "1" else " seconds")


def _instant_text(epoch: Any) -> "str | None":
    try:
        moment = _dt.datetime.fromtimestamp(float(epoch), _dt.timezone.utc)
    except (OverflowError, OSError, ValueError, TypeError):
        return None
    return moment.strftime("%Y-%m-%d %H:%M:%S UTC")


def wait_reading(deadlines: Any) -> dict:
    """The shortest relative wait and the earliest reset instant on a record.

    Rows the reader could not parse are skipped, so an unread header never
    becomes a stated wait.
    """
    rows = [r for r in deadlines or () if isinstance(r, dict)]
    waits = [r["seconds"] for r in rows
             if type(r.get("seconds")) in (int, float) and r["seconds"] >= 0]
    resets = [r["epoch"] for r in rows if type(r.get("epoch")) in (int, float)]
    return {"seconds": min(waits) if waits else None,
            "epoch": min(resets) if resets else None}


def _when(deadlines: Any) -> str:
    reading = wait_reading(deadlines)
    if reading["seconds"] is not None:
        return ("The provider asked for a wait of "
                + _seconds_text(reading["seconds"]) + " first.")
    instant = _instant_text(reading["epoch"]) if reading["epoch"] is not None else None
    if instant:
        return "The provider named " + instant + " as the time its limit resets."
    return "The provider gave no wait time."


def retry_advice(record: Any) -> str:
    """Whether trying again could help, and when, in plain words."""
    if not isinstance(record, dict):
        return "Whether trying again could help is unknown. " + NO_AUTO_RETRY
    retriable = record.get("retriable")
    if retriable is True:
        return ("Trying again could help. " + _when(record.get("deadlines"))
                + " " + NO_AUTO_RETRY)
    if retriable is False:
        change = _UNCHANGED.get(record.get("category"))
        if record.get("retriable_source") == "provider_header":
            return "Trying again will not help: the provider said not to retry."
        if change:
            return "Trying again will not help until " + change + "."
        return "Trying again with the same request will not help."
    return ("Whether trying again could help is unknown: the provider gave "
            "no retry signal for this failure. " + NO_AUTO_RETRY)


__all__ = ["NO_AUTO_RETRY", "retry_advice", "wait_reading"]

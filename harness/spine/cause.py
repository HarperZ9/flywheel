"""cause.py -- cause-and-effect fields, and the rules that recheck them.

A receipt that claims an effect names what was changed, the matched run it is
compared against, the measured difference, its interval, and a null-change run.
Every field is optional, so a record written before these fields existed still
verifies. A record that claims an effect must carry what the claim rests on.

    "cause": {
      "intervention": {"field": "temperature", "value": 0.7, "twin_value": 0.0},
      "run":   {"inputs": {...}, "outcome": 0.82},
      "twin_digest": "<canonical-record/1 sha256 of twin>",
      "twin":  {"inputs": {...}, "outcome": 0.70},
      "effect": 0.12,
      "interval": {"low": 0.05, "high": 0.19, "level": 0.95, "method": "..."},
      "placebo": {"change": {"field": "agent_name", "value": "b"},
                  "run": {"inputs": {...}, "outcome": 0.71},
                  "effect": 0.01, "interval": {...}}
    }

What the rules recheck: the twin matches its digest; run and twin differ in
the declared field and in no other; the declared values are the ones the runs
used; the effect is run outcome minus twin outcome; the interval is well formed
and holds the effect; the placebo differs from the twin only by its declared
inert change (or not at all) and its interval holds zero.

What they take as given: the outcomes and the interval bounds. Recomputing an
interval needs the resamples, which a receipt does not carry. Crucible's effect
claims (anatomy upgrade 2) are the place that recomputation belongs.
"""
from __future__ import annotations

import math

from ..verdict import Verdict
from .record import digest

_HEX = frozenset("0123456789abcdef")


def _hex64(value) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= _HEX


def _number(value) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def _close(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12)


def _run_ok(run) -> bool:
    return (isinstance(run, dict) and isinstance(run.get("inputs"), dict)
            and _number(run.get("outcome")))


def differing_fields(a: dict, b: dict) -> list[str]:
    """Input fields whose values differ, compared by canonical bytes."""
    return sorted(k for k in set(a) | set(b)
                  if (k in a) != (k in b)
                  or (k in a and digest(a[k]) != digest(b[k])))


def _interval(name: str, interval, value: float, checks: list) -> None:
    keys = ("low", "high", "level")
    if not isinstance(interval, dict) or not all(
            _number(interval.get(k)) for k in keys):
        checks.append((name, Verdict.UNVERIFIABLE,
                       "interval needs numeric low, high and level"))
        return
    low, high, level = (interval[k] for k in keys)
    if low > high or not 0 < level < 1:
        checks.append((name, Verdict.FAIL,
                       f"interval [{low}, {high}] at level {level} is malformed"))
    elif not low <= value <= high:
        checks.append((name, Verdict.FAIL,
                       f"{value} lies outside its interval [{low}, {high}]"))
    else:
        checks.append((name, Verdict.PASS,
                       f"{value} lies inside [{low}, {high}] at level {level}"))


def _twin(cause: dict, checks: list):
    """The embedded twin, if it matches its digest; else None with a check."""
    twin_digest = cause.get("twin_digest")
    if twin_digest is None:
        checks.append(("cause.twin", Verdict.UNVERIFIABLE,
                       "effect claimed without a twin digest"))
        return None
    if not _hex64(twin_digest):
        checks.append(("cause.twin", Verdict.UNVERIFIABLE,
                       "twin_digest is not a sha256 hex digest"))
        return None
    twin = cause.get("twin")
    if twin is None:
        checks.append(("cause.twin", Verdict.UNVERIFIABLE,
                       "twin not embedded, so the effect cannot be rechecked"))
        return None
    if digest(twin) != twin_digest:
        checks.append(("cause.twin", Verdict.FAIL,
                       "embedded twin does not match twin_digest"))
        return None
    if not _run_ok(twin):
        checks.append(("cause.twin", Verdict.UNVERIFIABLE,
                       "twin needs an inputs object and a numeric outcome"))
        return None
    checks.append(("cause.twin", Verdict.PASS, "twin matches its digest"))
    return twin


def _pairing(intervention, run: dict, twin: dict, checks: list) -> None:
    field = intervention.get("field") if isinstance(intervention, dict) else None
    if not isinstance(field, str) or not field:
        checks.append(("cause.intervention", Verdict.UNVERIFIABLE,
                       "no declared intervention field"))
        return
    diff = differing_fields(run["inputs"], twin["inputs"])
    if diff != [field]:
        checks.append(("cause.pairing", Verdict.FAIL,
                       f"run and twin differ in {diff or 'no field'}; "
                       f"the declared intervention is {field!r} alone"))
        return
    stated = (intervention.get("value"), intervention.get("twin_value"))
    used = (run["inputs"].get(field), twin["inputs"].get(field))
    if digest(stated[0]) != digest(used[0]) or digest(stated[1]) != digest(used[1]):
        checks.append(("cause.intervention", Verdict.FAIL,
                       f"declared {field!r} values {stated} differ from the "
                       f"values the runs used {used}"))
        return
    checks.append(("cause.pairing", Verdict.PASS,
                   f"run and twin differ in {field!r} alone"))


def _effect(cause: dict, run: dict, twin: dict, checks: list) -> None:
    effect = cause.get("effect")
    if not _number(effect):
        checks.append(("cause.effect", Verdict.UNVERIFIABLE,
                       "effect is not a finite number"))
        return
    expected = run["outcome"] - twin["outcome"]
    if not _close(effect, expected):
        checks.append(("cause.effect", Verdict.FAIL,
                       f"effect {effect} does not match its twin: run minus "
                       f"twin is {expected}"))
        return
    checks.append(("cause.effect", Verdict.PASS,
                   f"effect {effect} equals run minus twin"))
    if "interval" in cause:
        _interval("cause.interval", cause["interval"], effect, checks)


def _placebo(placebo, twin: dict, checks: list) -> None:
    if not isinstance(placebo, dict) or not _run_ok(placebo.get("run")):
        checks.append(("cause.placebo", Verdict.UNVERIFIABLE,
                       "placebo needs a run with inputs and a numeric outcome"))
        return
    change = placebo.get("change")
    allowed = [change["field"]] if isinstance(change, dict) and isinstance(
        change.get("field"), str) else []
    diff = differing_fields(placebo["run"]["inputs"], twin["inputs"])
    if diff and diff != allowed:
        checks.append(("cause.placebo", Verdict.FAIL,
                       f"placebo differs from the twin in {diff}; a null "
                       f"change may touch {allowed or 'no field'}"))
        return
    effect = placebo.get("effect")
    expected = placebo["run"]["outcome"] - twin["outcome"]
    if not _number(effect) or not _close(effect, expected):
        checks.append(("cause.placebo", Verdict.FAIL,
                       f"placebo effect {effect} does not match placebo minus "
                       f"twin, {expected}"))
        return
    interval = placebo.get("interval")
    if interval is None:
        verdict = Verdict.PASS if _close(effect, 0.0) else Verdict.UNDECIDED
        checks.append(("cause.placebo", verdict,
                       f"placebo effect {effect}, no interval given"))
        return
    _interval("cause.placebo.interval", interval, effect, checks)
    if checks[-1][1] is Verdict.PASS and not interval["low"] <= 0 <= interval["high"]:
        checks[-1] = ("cause.placebo.interval", Verdict.UNVERIFIABLE,
                      "CONFOUNDED: the null change moved the outcome, so the "
                      "pairing does not separate the intervention from noise")


def check_cause(cause) -> list[tuple[str, Verdict, str]]:
    """Recheck a cause block. An absent block yields no checks."""
    checks: list[tuple[str, Verdict, str]] = []
    if cause is None:
        return checks
    if not isinstance(cause, dict):
        return [("cause", Verdict.UNVERIFIABLE, "cause is not an object")]
    if "intervention" not in cause and "effect" in cause:
        checks.append(("cause.intervention", Verdict.UNVERIFIABLE,
                       "effect claimed without a declared intervention"))
    twin = _twin(cause, checks) if ("effect" in cause or "twin_digest" in cause
                                    or "twin" in cause) else None
    if twin is None:
        return checks
    run = cause.get("run")
    if not _run_ok(run):
        checks.append(("cause.run", Verdict.UNVERIFIABLE,
                       "run needs an inputs object and a numeric outcome"))
        return checks
    if "intervention" in cause:
        _pairing(cause["intervention"], run, twin, checks)
    if "effect" in cause:
        _effect(cause, run, twin, checks)
    if "placebo" in cause:
        _placebo(cause["placebo"], twin, checks)
    return checks

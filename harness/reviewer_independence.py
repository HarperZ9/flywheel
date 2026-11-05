"""reviewer_independence -- does a second reader add a catch, given the evidence it shares?

A second checker that reads the same evidence as the first repeats the first
one's errors. Commenters on six unrelated posts made that point independently,
and the society lane measured it: a second reader catches a lie the first one
cleared only through evidence the first did not read. With

    p     the share of known lies the first checker clears (its miss rate),
    acc   how often the second reader is right on its own evidence,
    rho   the share of the second reader's evidence the first already read,

the second reader catches p * acc * (1 - rho) of the lies read. It pays when
that reaches a floor (0.05 by default), so the stop point is

    rho* = 1 - floor / (p * acc).

The society lane's base policy measured p = 0.247 and, at acc 0.8, a catch of
0.100 at rho 0.5 and a stop point of 0.75; the formula held within 0.01 of the
measured catch in every arm. Tests reproduce those numbers.

Subject: {"first": [evidence ids], "second": [evidence ids]}, where an id is
anything stable that names one piece of evidence (a file sha256, a URL, a
record id). Spec: "p" and "acc", each a number or {"k": int, "n": int}; with
counts the verdict uses Wilson 95% bounds. Optional "floor" (default 0.05).

Verdicts, in the check-receipt vocabulary:
  PASS          the catch's lower bound reaches the floor: add the second reader
  FAIL          the catch's upper bound sits below the floor: the second reader
                shares too much evidence to pay
  UNVERIFIABLE  an input is missing, or the interval straddles the floor
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .checks.receipt import FAIL, PASS, UNVERIFIABLE, CheckReceipt, digest
from .trace_observation.intervals import wilson

FLOOR = 0.05
CHECK = "reviewer_independence"


def _rate(value, name: str) -> tuple[float, float, float]:
    """(point, low, high) from a number or a {"k", "n"} count."""
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a number or a count")
    if isinstance(value, (int, float)):
        if not 0 <= value <= 1:
            raise ValueError(f"{name} must lie in [0, 1]")
        return float(value), float(value), float(value)
    if isinstance(value, dict) and isinstance(value.get("k"), int) and isinstance(value.get("n"), int):
        lo, hi = wilson(value["k"], value["n"])
        return value["k"] / value["n"], lo, hi
    raise ValueError(f"{name} must be a number or {{'k': int, 'n': int}}")


def overlap(first, second) -> float:
    """Share of the second reader's distinct evidence that the first already read."""
    b = set(second)
    return len(b & set(first)) / len(b)


def stop_point(p: float, acc: float, floor: float = FLOOR) -> float:
    """rho*: the overlap above which the second reader catches under `floor`.
    Below zero means no overlap is low enough."""
    return 1 - floor / (p * acc) if p * acc > 0 else float("-inf")


def measure(subject, spec: dict) -> dict:
    """The numbers behind the verdict. Raises ValueError on a malformed input."""
    if not isinstance(subject, dict):
        raise ValueError("subject must be {'first': [...], 'second': [...]}")
    first, second = subject.get("first"), subject.get("second")
    if not isinstance(first, list) or not isinstance(second, list) or not second:
        raise ValueError("subject needs a 'first' list and a non-empty 'second' list")
    floor = float(spec.get("floor", FLOOR))
    p, p_lo, p_hi = _rate(spec.get("p"), "p")
    acc, a_lo, a_hi = _rate(spec.get("acc"), "acc")
    rho = overlap(first, second)
    return {"rho": rho, "floor": floor, "p": p, "acc": acc,
            "catch": p * acc * (1 - rho),
            "catch_low": p_lo * a_lo * (1 - rho), "catch_high": p_hi * a_hi * (1 - rho),
            "stop_point": stop_point(p, acc, floor),
            "shared": len(set(second) & set(first)), "second_items": len(set(second))}


def independence_check(subject, spec: dict) -> tuple[str, str, str]:
    """The check-library signature: (verdict, code, reason)."""
    if spec.get("p") is None or spec.get("acc") is None:
        return UNVERIFIABLE, "no_rates", "the spec needs p (first checker's miss rate) and acc"
    try:
        m = measure(subject, spec)
    except ValueError as exc:
        return UNVERIFIABLE, "malformed", str(exc)
    line = (f"overlap {m['rho']:.3f} ({m['shared']} of {m['second_items']}), stop point "
            f"{m['stop_point']:.3f}, catch {m['catch']:.3f} "
            f"({m['catch_low']:.3f} to {m['catch_high']:.3f}) against floor {m['floor']:.3f}")
    if m["catch_low"] >= m["floor"]:
        return PASS, "second_reader_pays", line
    if m["catch_high"] < m["floor"]:
        return FAIL, "second_reader_redundant", line
    return UNVERIFIABLE, "interval_straddles_floor", line


def run(subject, spec: dict) -> CheckReceipt:
    verdict, code, reason = independence_check(subject, spec)
    return CheckReceipt(check=CHECK, verdict=verdict, code=code, reason=reason,
                        subject_sha256=digest(subject), spec_sha256=digest(spec))


def main(argv=None, stdout=None) -> int:
    stdout = stdout or sys.stdout
    ap = argparse.ArgumentParser(prog="python -m harness.reviewer_independence",
                                 description="Should a second reader be added, given shared evidence?")
    ap.add_argument("file", help='JSON with "subject" and "spec"')
    a = ap.parse_args(argv)
    data = json.loads(Path(a.file).read_text(encoding="utf-8"))
    receipt = run(data.get("subject"), data.get("spec") or {})
    stdout.write(json.dumps(receipt.to_dict(), indent=1) + "\n")
    return {PASS: 0, FAIL: 1}.get(receipt.verdict, 2)


if __name__ == "__main__":
    sys.exit(main())

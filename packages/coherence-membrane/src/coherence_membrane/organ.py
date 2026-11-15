"""The organ contract and the selftest harness.

An organ is a perception source: given a subject, it emits witnessed
Observations.  It is INERT -- it reads and reports; it never mutates the world
and never grants authority.

The selftest is not optional.  The membrane doctrine's hardest-won rule is that
*an unverified membrane is net-negative* -- it launders falsehood with
ground-truth authority.  So every organ must ship a `selftest()` that re-derives
its own claims from raw input and can fail.  An organ that has not passed its
selftest must not be trusted as an oracle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from .observation import Observation


@dataclass(frozen=True)
class Check:
    label: str
    ok: bool
    detail: str = ""


@dataclass(frozen=True)
class SelftestResult:
    organ: str
    checks: list[Check] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.ok for c in self.checks) and len(self.checks) > 0

    def to_dict(self) -> dict:
        return {
            "organ": self.organ,
            "passed": self.passed,
            "checks": [{"label": c.label, "ok": c.ok, "detail": c.detail} for c in self.checks],
        }


@runtime_checkable
class Organ(Protocol):
    """An inert perception source.

    name      -- stable identifier, also stamped onto every Observation.
    observe   -- read `subject` and return witnessed Observations (never mutate).
    selftest  -- re-derive the organ's own claims from known input; must be able
                to fail.  Returns a SelftestResult.
    """

    name: str

    def observe(self, subject) -> list[Observation]: ...

    def selftest(self) -> SelftestResult: ...


def run_selftests(organs: list[Organ]) -> dict:
    """Run every organ's selftest and aggregate.

    Returns {"passed": bool, "results": [SelftestResult.to_dict(), ...]}.
    `passed` is True only if every organ has at least one check and all pass --
    fail-closed: an organ with no checks does NOT pass.
    """
    results = [organ.selftest() for organ in organs]
    return {
        "passed": all(r.passed for r in results) and len(results) > 0,
        "results": [r.to_dict() for r in results],
    }

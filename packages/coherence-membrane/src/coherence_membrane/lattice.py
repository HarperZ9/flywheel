"""Formal verification of the verdict lattices -- proofs, not assertions.

Every adjudication in the membrane returns a value from a small CLOSED set:
drift is MATCH / DRIFT / UNVERIFIABLE, a receipt is VALID / DRIFT / UNVERIFIABLE,
a provenance graph is VALID / BROKEN / UNVERIFIABLE. The membrane's safety rests
on three claims about those sets, claims the rest of the code merely *asserts* in
docstrings ("fail-closed", "never a silent MATCH", "composition never amplifies
trust"). This module turns the claims into machine-checked proofs.

The carriers are finite (three elements each), so exhaustive enumeration is a
COMPLETE decision procedure -- every law is checked over every tuple, not sampled.
For these finite, non-temporal laws that is exactly what an explicit-state model
checker (TLA+/TLC) would do -- enumerate the whole state space -- so the enumeration
here IS that check, executed directly on every `pytest`, with no separate spec or
toolchain to rot. (Liveness/temporal checking would add nothing: the laws are
algebraic, not temporal.)

Two kinds of guarantee live here; the THIRD (binding the algebra to the real
adjudicators -- compare_drift, compare_composite, verify_receipt, verify(),
baseline.check, _assess, trace_events) lives in tests/test_lattice*.py, which
prove the implementations equal / refine these structures.

  1. Lattice well-formedness -- each verdict set, under its affirmation order
     (most-affirmative at top), is a genuine bounded lattice: the order is a
     partial order, every pair has a unique meet and join, and there is a top and
     a bottom. Proved by enumeration; for a chain this is easy, which is the
     point -- the order is made explicit and checkable, not assumed.
  2. Meet = fail-closed combination -- the meet (greatest lower bound) is the
     attenuation operator: combining verdicts can only move DOWN the order. It is
     commutative, associative, idempotent; the affirmative top is its identity
     (it composes away) and the bottom is absorbing (a positive detection
     dominates); and it is MONOTONE -- degrading any input never improves the
     result. So composition cannot launder a worse observation set into a better
     verdict -- a theorem, not a comment.

Inert and advisory like everything else: it computes and proves; it decides
nothing and grants no authority. Stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Iterable

from .agent_loop import ADJUST, CONVERGED, INDETERMINATE
from .phash import DRIFT, MATCH, UNVERIFIABLE
from .provenance import BROKEN
from .receipt import VALID

# --- the affirmation order, bottom -> top ---------------------------------
# Bottom = the most conservative verdict (a positive detection of a problem, or
# the strongest reason to deny). Top = the most affirmative (the strongest
# positive statement, the only verdict a downstream gate may treat as "allow").
# UNVERIFIABLE always sits between: absence of evidence, never affirmative.


@dataclass(frozen=True)
class Check:
    """One proven (or refuted) law. `detail` carries a counterexample on failure."""

    name: str
    ok: bool
    detail: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "ok": self.ok, "detail": self.detail}


@dataclass(frozen=True)
class LatticeProof:
    subject: str
    checks: tuple[Check, ...]

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)

    def failures(self) -> list[Check]:
        return [c for c in self.checks if not c.ok]

    def to_dict(self) -> dict:
        return {"subject": self.subject, "ok": self.ok,
                "checks": [c.to_dict() for c in self.checks]}


class Lattice:
    """A finite bounded lattice over verdict strings, given as an ascending chain.

    `chain[0]` is the bottom (most conservative), `chain[-1]` the top (most
    affirmative). The order, meet and join are DERIVED from the chain via a
    general partial-order construction (not special-cased to chains), so
    prove_is_lattice() genuinely verifies lattice-ness rather than assuming it.
    """

    def __init__(self, name: str, chain: Iterable[str]) -> None:
        self.name = name
        self.chain: tuple[str, ...] = tuple(chain)
        if len(set(self.chain)) != len(self.chain):
            raise ValueError(f"{name}: chain has duplicate elements {self.chain}")
        self.elements: frozenset[str] = frozenset(self.chain)
        # a <= b for all pairs at or below b in the chain (the explicit relation).
        self._order: frozenset[tuple[str, str]] = frozenset(
            (a, b) for i, a in enumerate(self.chain) for b in self.chain[i:]
        )

    @property
    def bottom(self) -> str:
        return self.chain[0]

    @property
    def top(self) -> str:
        return self.chain[-1]

    def leq(self, a: str, b: str) -> bool:
        return (a, b) in self._order

    def _glb(self, a: str, b: str) -> str | None:
        """Greatest lower bound from the order alone (None if absent/ambiguous)."""
        lowers = [x for x in self.elements if self.leq(x, a) and self.leq(x, b)]
        greatest = [m for m in lowers if all(self.leq(x, m) for x in lowers)]
        return greatest[0] if len(greatest) == 1 else None

    def _lub(self, a: str, b: str) -> str | None:
        uppers = [x for x in self.elements if self.leq(a, x) and self.leq(b, x)]
        least = [m for m in uppers if all(self.leq(m, x) for x in uppers)]
        return least[0] if len(least) == 1 else None

    def meet(self, a: str, b: str) -> str:
        """Fail-closed combination of two verdicts: their greatest lower bound."""
        m = self._glb(a, b)
        if m is None:
            raise ValueError(f"{self.name}: no unique meet for {a!r},{b!r}")
        return m

    def join(self, a: str, b: str) -> str:
        j = self._lub(a, b)
        if j is None:
            raise ValueError(f"{self.name}: no unique join for {a!r},{b!r}")
        return j

    def fold_meet(self, verdicts: Iterable[str]) -> str:
        """Meet over many verdicts; the empty fold is the identity (top).

        This is the pure model of fail-closed aggregation: the result is no more
        affirmative than the least-affirmative input. NOTE the empty case returns
        the top -- an aggregator that must fail closed on *no* evidence (e.g.
        compare_composite on an empty baseline) deliberately returns something
        STRICTLY BELOW this (UNVERIFIABLE), a safe tightening, never above it.
        """
        acc = self.top
        for v in verdicts:
            acc = self.meet(acc, v)
        return acc


# The three combinable/gating lattices. Same shape, same UNVERIFIABLE-in-the-
# middle discipline; the top is the only verdict a downstream gate may allow on.
DRIFT_LATTICE = Lattice("drift", (DRIFT, UNVERIFIABLE, MATCH))
RECEIPT_LATTICE = Lattice("receipt", (DRIFT, UNVERIFIABLE, VALID))
GRAPH_LATTICE = Lattice("graph", (BROKEN, UNVERIFIABLE, VALID))

# The disposition set is a CLOSED CLASSIFICATION, not a combined lattice -- nothing
# in the codebase takes a meet of dispositions. Its safety guarantee (proved in
# tests against _assess) is reachability: INDETERMINATE only from an UNVERIFIABLE
# look, CONVERGED only from MATCH or within-tolerance drift -- never a silent
# convergence on an uncomparable result.
DISPOSITIONS = frozenset({CONVERGED, ADJUST, INDETERMINATE})

ALL_LATTICES = (DRIFT_LATTICE, RECEIPT_LATTICE, GRAPH_LATTICE)


# --- proof checkers (exhaustive over the finite carrier) ------------------


def prove_partial_order(L: Lattice) -> list[Check]:
    e = L.elements
    refl = all(L.leq(a, a) for a in e)
    antisym = all(a == b for a in e for b in e if L.leq(a, b) and L.leq(b, a))
    trans = all(
        L.leq(a, c)
        for a in e for b in e for c in e
        if L.leq(a, b) and L.leq(b, c)
    )
    return [
        Check(f"{L.name}: order is reflexive", refl),
        Check(f"{L.name}: order is antisymmetric", antisym),
        Check(f"{L.name}: order is transitive", trans),
    ]


def prove_is_lattice(L: Lattice) -> list[Check]:
    e = L.elements
    meets_exist = all(L._glb(a, b) is not None for a in e for b in e)
    joins_exist = all(L._lub(a, b) is not None for a in e for b in e)
    bounded = (
        all(L.leq(L.bottom, a) for a in e) and all(L.leq(a, L.top) for a in e)
    )
    return [
        Check(f"{L.name}: every pair has a unique meet", meets_exist),
        Check(f"{L.name}: every pair has a unique join", joins_exist),
        Check(f"{L.name}: bounded (bottom below all, top above all)", bounded),
    ]


def prove_meet_laws(L: Lattice) -> list[Check]:
    """The attenuation laws -- the heart of 'composition never amplifies trust'."""
    e = list(L.elements)

    def _ctr(pred, *spaces) -> str:
        for tup in product(*spaces):
            if not pred(*tup):
                return f"counterexample {tup}"
        return ""

    commutative = _ctr(lambda a, b: L.meet(a, b) == L.meet(b, a), e, e)
    associative = _ctr(
        lambda a, b, c: L.meet(L.meet(a, b), c) == L.meet(a, L.meet(b, c)), e, e, e
    )
    idempotent = _ctr(lambda a: L.meet(a, a) == a, e)
    identity_top = _ctr(lambda a: L.meet(L.top, a) == a, e)
    absorb_bottom = _ctr(lambda a: L.meet(L.bottom, a) == L.bottom, e)
    # meet is <= both arguments (it attenuates, never amplifies)
    lowers = _ctr(lambda a, b: L.leq(L.meet(a, b), a) and L.leq(L.meet(a, b), b), e, e)
    # monotone: degrading any input never improves the meet
    monotone = _ctr(
        lambda a, ap, b, bp: (not (L.leq(a, ap) and L.leq(b, bp)))
        or L.leq(L.meet(a, b), L.meet(ap, bp)),
        e, e, e, e,
    )
    return [
        Check(f"{L.name}: meet is commutative", not commutative, commutative),
        Check(f"{L.name}: meet is associative", not associative, associative),
        Check(f"{L.name}: meet is idempotent", not idempotent, idempotent),
        Check(f"{L.name}: top is the meet identity (it composes away)",
              not identity_top, identity_top),
        Check(f"{L.name}: bottom is absorbing (a positive detection dominates)",
              not absorb_bottom, absorb_bottom),
        Check(f"{L.name}: meet attenuates (result <= every input)", not lowers, lowers),
        Check(f"{L.name}: meet is monotone (degrading input never improves it)",
              not monotone, monotone),
    ]


def prove_lattice(L: Lattice) -> LatticeProof:
    checks = prove_partial_order(L) + prove_is_lattice(L) + prove_meet_laws(L)
    return LatticeProof(L.name, tuple(checks))


def prove_all() -> list[LatticeProof]:
    """Every abstract lattice proof. Bound to the real adjudicators in tests."""
    return [prove_lattice(L) for L in ALL_LATTICES]


def _report() -> int:
    proofs = prove_all()
    lines: list[str] = []
    for p in proofs:
        lines.append(f"[{'ok ' if p.ok else 'FAIL'}] lattice {p.subject!r}: "
                     f"{sum(c.ok for c in p.checks)}/{len(p.checks)} laws")
        for c in p.failures():
            lines.append(f"    FAIL {c.name}: {c.detail}")
    ok = all(p.ok for p in proofs)
    lines.append("ALL LATTICE PROOFS PASS" if ok else "LATTICE PROOFS FAILED")
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":  # python -m coherence_membrane.lattice
    raise SystemExit(_report())

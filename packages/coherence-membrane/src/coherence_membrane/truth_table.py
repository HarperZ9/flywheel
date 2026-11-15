"""Native brute-force truth-table decision -- the independent peer to the DPLL oracle.

Tier-3 cross-check needs a SECOND method whose correctness is self-evident: this
enumerates every total assignment and applies `evaluate` directly (the truth table
IS the definition of validity/SAT). It shares no verdict machinery with `solve` --
DPLL uses `_peval` (3-valued partial eval) + branching; this uses `evaluate`
(2-valued total) + enumeration -- so a bug in DPLL's pruning cannot hide here.
Exponential, hence atom-capped: the cross-check verifies a small, certain core."""
from __future__ import annotations

import itertools

from .certificate import Certificate, Verdict
from .propositional import Not, OverCap, atoms, evaluate, show

_ORACLE = "truth-table-v1"


def tt_solve(formula, *, max_atoms: int = 16) -> dict | None:
    """A satisfying assignment by exhaustive enumeration, or None if UNSAT.
    Raises OverCap above the atom cap (kept low -- this is 2**n)."""
    names = sorted(atoms(formula))
    if len(names) > max_atoms:
        raise OverCap(f"{len(names)} atoms > cap {max_atoms}")
    for combo in itertools.product((False, True), repeat=len(names)):
        assignment = dict(zip(names, combo))
        if evaluate(formula, assignment):
            return assignment
    return None


def _model_evidence(prefix: str, model: dict) -> tuple[tuple[str, str], ...]:
    return tuple((f"{prefix}:{k}", str(int(model[k]))) for k in sorted(model))


def tt_check_sat(formula, *, max_atoms: int = 16) -> Certificate:
    """Satisfiable? VERIFIED + model, REFUTED if unsat, UNVERIFIABLE over cap."""
    claim = f"SAT {show(formula)}"
    try:
        model = tt_solve(formula, max_atoms=max_atoms)
    except OverCap as exc:
        return Certificate(claim, Verdict.UNVERIFIABLE, _ORACLE, (("reason", str(exc)),))
    if model is None:
        return Certificate(claim, Verdict.REFUTED, _ORACLE, (("unsat", "no satisfying assignment"),))
    return Certificate(claim, Verdict.VERIFIED, _ORACLE, _model_evidence("model", model))


def tt_check_validity(formula, *, max_atoms: int = 16) -> Certificate:
    """Valid iff Not(formula) has no satisfying assignment (exhaustive)."""
    claim = show(formula)
    try:
        model = tt_solve(Not(formula), max_atoms=max_atoms)
    except OverCap as exc:
        return Certificate(claim, Verdict.UNVERIFIABLE, _ORACLE, (("reason", str(exc)),))
    if model is None:
        return Certificate(claim, Verdict.VERIFIED, _ORACLE, (("valid", "negation unsatisfiable"),))
    return Certificate(claim, Verdict.REFUTED, _ORACLE, _model_evidence("counterexample", model))

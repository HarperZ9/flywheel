"""Native propositional logic: formula AST, evaluation, DPLL, Certificate checks.

Sound + complete + decidable for propositional logic. The deductive oracle (tier 1)
of the verifier ladder; soundness is enforced (never a false VERIFIED)."""
from __future__ import annotations

from dataclasses import dataclass

from .certificate import Certificate, Verdict


@dataclass(frozen=True)
class Var:
    name: str


@dataclass(frozen=True)
class Const:
    value: bool


@dataclass(frozen=True)
class Not:
    x: object


@dataclass(frozen=True)
class And:
    a: object
    b: object


@dataclass(frozen=True)
class Or:
    a: object
    b: object


@dataclass(frozen=True)
class Implies:
    a: object
    b: object


@dataclass(frozen=True)
class Iff:
    a: object
    b: object


_BINARY = (And, Or, Implies, Iff)
_FORMULA_TYPES = (Var, Const, Not, And, Or, Implies, Iff)


def is_formula(x) -> bool:
    return isinstance(x, _FORMULA_TYPES)


def atoms(f) -> set[str]:
    if isinstance(f, Const):
        return set()
    if isinstance(f, Var):
        return {f.name}
    if isinstance(f, Not):
        return atoms(f.x)
    if isinstance(f, _BINARY):
        return atoms(f.a) | atoms(f.b)
    raise TypeError(f"not a formula: {f!r}")


def evaluate(f, a: dict) -> bool:
    """Evaluate under a TOTAL assignment (every atom present)."""
    if isinstance(f, Const):
        return f.value
    if isinstance(f, Var):
        return a[f.name]
    if isinstance(f, Not):
        return not evaluate(f.x, a)
    if isinstance(f, And):
        return evaluate(f.a, a) and evaluate(f.b, a)
    if isinstance(f, Or):
        return evaluate(f.a, a) or evaluate(f.b, a)
    if isinstance(f, Implies):
        return (not evaluate(f.a, a)) or evaluate(f.b, a)
    if isinstance(f, Iff):
        return evaluate(f.a, a) == evaluate(f.b, a)
    raise TypeError(f"not a formula: {f!r}")


def show(f) -> str:
    if isinstance(f, Const):
        return "T" if f.value else "F"
    if isinstance(f, Var):
        return f.name
    if isinstance(f, Not):
        return f"~{show(f.x)}"
    if isinstance(f, And):
        return f"({show(f.a)} & {show(f.b)})"
    if isinstance(f, Or):
        return f"({show(f.a)} | {show(f.b)})"
    if isinstance(f, Implies):
        return f"({show(f.a)} -> {show(f.b)})"
    if isinstance(f, Iff):
        return f"({show(f.a)} <-> {show(f.b)})"
    raise TypeError(f"not a formula: {f!r}")


class OverCap(Exception):
    """Raised when a formula exceeds the atom cap; the caller maps it to
    UNVERIFIABLE (never a hang, never a false verdict)."""


def _peval(f, a: dict):
    """Three-valued partial evaluation: True/False if determined by the partial
    assignment `a` alone, else None. A True/False result is monotone -- it holds
    under every completion -- which is what makes pruning sound."""
    if isinstance(f, Const):
        return f.value
    if isinstance(f, Var):
        return a.get(f.name)
    if isinstance(f, Not):
        v = _peval(f.x, a)
        return None if v is None else not v
    if isinstance(f, And):
        va, vb = _peval(f.a, a), _peval(f.b, a)
        if va is False or vb is False:
            return False
        if va is True and vb is True:
            return True
        return None
    if isinstance(f, Or):
        va, vb = _peval(f.a, a), _peval(f.b, a)
        if va is True or vb is True:
            return True
        if va is False and vb is False:
            return False
        return None
    if isinstance(f, Implies):
        va, vb = _peval(f.a, a), _peval(f.b, a)
        if va is False or vb is True:
            return True
        if va is True and vb is False:
            return False
        return None
    if isinstance(f, Iff):
        va, vb = _peval(f.a, a), _peval(f.b, a)
        if va is None or vb is None:
            return None
        return va == vb
    raise TypeError(f"not a formula: {f!r}")


def solve(formula, *, max_atoms: int = 20) -> dict | None:
    """DPLL-style search: a satisfying assignment (completed over all atoms) or
    None if UNSAT. Raises OverCap above the atom cap."""
    names = sorted(atoms(formula))
    if len(names) > max_atoms:
        raise OverCap(f"{len(names)} atoms > cap {max_atoms}")
    assignment: dict[str, bool] = {}

    def search() -> bool:
        v = _peval(formula, assignment)
        if v is True:
            return True
        if v is False:
            return False
        atom = next(n for n in names if n not in assignment)
        for val in (False, True):
            assignment[atom] = val
            if search():
                return True
            del assignment[atom]
        return False

    if not search():
        return None
    return {n: assignment.get(n, False) for n in names}   # complete the partial model


_ORACLE = "propositional-dpll-v1"


def _model_evidence(prefix: str, model: dict) -> tuple[tuple[str, str], ...]:
    return tuple((f"{prefix}:{k}", str(int(model[k]))) for k in sorted(model))


def check_sat(formula, *, max_atoms: int = 20) -> Certificate:
    """Satisfiable? VERIFIED + model, REFUTED if unsat, UNVERIFIABLE over cap."""
    claim = f"SAT {show(formula)}"
    try:
        model = solve(formula, max_atoms=max_atoms)
    except OverCap as exc:
        return Certificate(claim, Verdict.UNVERIFIABLE, _ORACLE, (("reason", str(exc)),))
    if model is None:
        return Certificate(claim, Verdict.REFUTED, _ORACLE, (("unsat", "no satisfying assignment"),))
    return Certificate(claim, Verdict.VERIFIED, _ORACLE, _model_evidence("model", model))


def check_validity(formula, *, max_atoms: int = 20, backend=None) -> Certificate:
    """Valid? VERIFIED if the negation is unsat; REFUTED + counterexample if
    falsifiable; over cap, consult an optional `backend` (formula->Certificate|None)
    then UNVERIFIABLE.

    SOUNDNESS: the native path never returns VERIFIED unless the negation is proven
    unsat. A supplied `backend` is part of the TRUSTED BASE -- its verdict is returned
    as-is, so supply only a sound oracle. The shipped organ passes no backend, so it
    is unconditionally sound."""
    claim = show(formula)
    try:
        model = solve(Not(formula), max_atoms=max_atoms)
    except OverCap as exc:
        if backend is not None:
            cert = backend(formula)
            if cert is not None:
                return cert
        return Certificate(claim, Verdict.UNVERIFIABLE, _ORACLE, (("reason", str(exc)),))
    if model is None:
        return Certificate(claim, Verdict.VERIFIED, _ORACLE, (("valid", "negation unsatisfiable"),))
    return Certificate(claim, Verdict.REFUTED, _ORACLE, _model_evidence("counterexample", model))

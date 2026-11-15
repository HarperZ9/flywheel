"""Native quantifier-free linear rational arithmetic (QF-LRA), conjunctive fragment,
with PROOF-CARRYING verdicts.

Propositional logic cannot reason over `2x + 3y <= 5`. This decides conjunctions of
linear constraints by Fourier-Motzkin elimination -- but does NOT trust the solver:
every verdict carries a WITNESS a tiny independent checker re-verifies. Feasible -> a
rational model (checked by substitution); infeasible -> a Farkas certificate (a
nonnegative/signed combination collapsing the system to `0 (op) negative`, checked by
arithmetic). VERIFIED only if the witness checks, so a bug anywhere in elimination
yields an invalid witness -> UNVERIFIABLE, never a false VERIFIED. The trusted base is
the checker, not the solver. Rational-exact (fractions.Fraction)."""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from .certificate import Certificate, Verdict
from .composition import compose

_ORACLE = "lra-fm-v1"
_ROW_CAP = 4000


@dataclass(frozen=True)
class LinearConstraint:
    """sum(coeff*var) op rhs, op in {"<=","<","="}; terms sorted, nonzero, Fraction."""

    terms: tuple
    op: str
    rhs: Fraction

    def coeff(self, var: str) -> Fraction:
        for v, c in self.terms:
            if v == var:
                return c
        return Fraction(0)

    @property
    def variables(self) -> tuple:
        return tuple(v for v, _ in self.terms)

    def evaluate(self, point: dict) -> bool:
        lhs = sum((c * Fraction(point[v]) for v, c in self.terms), Fraction(0))
        if self.op == "<=":
            return lhs <= self.rhs
        if self.op == "<":
            return lhs < self.rhs
        return lhs == self.rhs


def constraint(coeffs: dict, op: str, rhs) -> LinearConstraint:
    """Normalized builder: >=/> are flipped to <=/< (x-1); zero coeffs dropped; sorted."""
    rhs = Fraction(rhs)
    items = {v: Fraction(c) for v, c in coeffs.items() if Fraction(c) != 0}
    if op in (">=", ">"):
        items = {v: -c for v, c in items.items()}
        rhs = -rhs
        op = "<=" if op == ">=" else "<"
    if op not in ("<=", "<", "="):
        raise ValueError(f"bad op {op!r}")
    return LinearConstraint(tuple(sorted(items.items())), op, rhs)


def negate(c: LinearConstraint):
    """Single-constraint negation, or None for '=' (its negation is a disjunction)."""
    coeffs = {v: cc for v, cc in c.terms}
    if c.op == "<=":
        return constraint(coeffs, ">", c.rhs)
    if c.op == "<":
        return constraint(coeffs, ">=", c.rhs)
    return None


@dataclass(frozen=True)
class FMResult:
    status: str
    model: dict | None = None
    multipliers: dict | None = None
    reason: str = ""


def _rows(constraints):
    """Each constraint -> working rows (coeffs, strict, rhs, combo) in `sum<=rhs` form;
    '=' splits into <= and >= (the latter as <= via x-1) with signed combo over its index."""
    out = []
    for i, c in enumerate(constraints):
        coeffs = {v: cc for v, cc in c.terms}
        if c.op in ("<=", "<"):
            out.append((dict(coeffs), c.op == "<", c.rhs, {i: Fraction(1)}))
        else:
            out.append((dict(coeffs), False, c.rhs, {i: Fraction(1)}))
            out.append(({v: -cc for v, cc in coeffs.items()}, False, -c.rhs, {i: Fraction(-1)}))
    return out


def _combine(U, L, mu, ml):
    """mu*U + ml*L (mu,ml > 0), in `sum<=rhs` form, summing combos."""
    (uc, us, ur, ucombo), (lc, ls, lr, lcombo) = U, L
    coeffs = {}
    for v, c in uc.items():
        coeffs[v] = coeffs.get(v, Fraction(0)) + mu * c
    for v, c in lc.items():
        coeffs[v] = coeffs.get(v, Fraction(0)) + ml * c
    coeffs = {v: c for v, c in coeffs.items() if c != 0}
    combo = {}
    for k, val in ucombo.items():
        combo[k] = combo.get(k, Fraction(0)) + mu * val
    for k, val in lcombo.items():
        combo[k] = combo.get(k, Fraction(0)) + ml * val
    return (coeffs, us or ls, mu * ur + ml * lr, combo)


def _pick(lower, upper):
    if lower is None and upper is None:
        return Fraction(0)
    if lower is None:
        ub, us = upper
        return ub - 1 if us else ub
    if upper is None:
        lb, ls = lower
        return lb + 1 if ls else lb
    (lb, _), (ub, _) = lower, upper
    return (lb + ub) / 2 if lb < ub else lb


def _extract_model(eliminated):
    model = {}
    for var, snap in reversed(eliminated):
        lower = upper = None
        for coeffs, strict, rhs, _ in snap:
            cv = coeffs.get(var, Fraction(0))
            if cv == 0:
                continue
            resid = rhs - sum(c * model[v] for v, c in coeffs.items() if v != var and v in model)
            bound = resid / cv
            if cv > 0:
                if upper is None or bound < upper[0] or (bound == upper[0] and strict):
                    upper = (bound, strict)
            else:
                if lower is None or bound > lower[0] or (bound == lower[0] and strict):
                    lower = (bound, strict)
        model[var] = _pick(lower, upper)
    return model


def fourier_motzkin(constraints, *, max_rows: int = _ROW_CAP) -> FMResult:
    rows = _rows(constraints)
    variables = sorted({v for c in constraints for v in c.variables})
    eliminated = []
    for var in variables:
        pos = [r for r in rows if r[0].get(var, Fraction(0)) > 0]
        neg = [r for r in rows if r[0].get(var, Fraction(0)) < 0]
        zero = [r for r in rows if r[0].get(var, Fraction(0)) == 0]
        eliminated.append((var, rows))
        new_rows = list(zero)
        for U in pos:
            for L in neg:
                new_rows.append(_combine(U, L, -L[0][var], U[0][var]))
                if len(new_rows) > max_rows:
                    return FMResult("overcap", reason=f"> {max_rows} rows")
        rows = new_rows
    for coeffs, strict, rhs, combo in rows:
        if (strict and rhs <= 0) or ((not strict) and rhs < 0):
            return FMResult("unsat", multipliers={k: v for k, v in combo.items() if v != 0})
    return FMResult("sat", model=_extract_model(eliminated))


def _show(c: LinearConstraint) -> str:
    lhs = " + ".join(f"{coeff}*{v}" for v, coeff in c.terms) or "0"
    return f"{lhs} {c.op} {c.rhs}"


def check_model(constraints, model) -> bool:
    """Trusted check: does the model satisfy every constraint? (Pure substitution.)"""
    try:
        return all(c.evaluate(model) for c in constraints)
    except (KeyError, TypeError, ZeroDivisionError, ValueError):
        return False


def check_farkas(constraints, multipliers) -> bool:
    """Trusted check: nonneg multipliers on <=/< (free on =), coefficients cancel to 0,
    and the constant is a contradiction with correct strictness."""
    combo_coeffs: dict = {}
    combo_rhs = Fraction(0)
    strict = False
    try:
        for i, c in enumerate(constraints):
            m = Fraction(multipliers.get(i, 0))
            if m == 0:
                continue
            if c.op in ("<=", "<") and m < 0:
                return False
            for v, coeff in c.terms:
                combo_coeffs[v] = combo_coeffs.get(v, Fraction(0)) + m * coeff
            combo_rhs += m * c.rhs
            if c.op == "<" and m > 0:
                strict = True
    except (TypeError, ValueError, ZeroDivisionError):
        return False
    if any(v != 0 for v in combo_coeffs.values()):
        return False
    return combo_rhs <= 0 if strict else combo_rhs < 0


def _claim(prefix, cons):
    body = " ∧ ".join(_show(c) for c in cons) if cons else "(empty)"
    return f"{prefix}: {body}"


def check_feasible(constraints) -> Certificate:
    """Feasible? VERIFIED + checked model; REFUTED + checked Farkas; else UNVERIFIABLE.
    Proof-carrying: the verdict is only as good as the independently-checked witness."""
    cons = list(constraints)
    claim = _claim("feasible", cons)
    try:
        res = fourier_motzkin(cons)
    except Exception as exc:
        return Certificate(claim, Verdict.UNVERIFIABLE, _ORACLE, (("error", repr(exc)),))
    if res.status == "sat" and res.model is not None and check_model(cons, res.model):
        ev = tuple((f"model:{v}", str(res.model[v])) for v in sorted(res.model))
        return Certificate(claim, Verdict.VERIFIED, _ORACLE, ev or (("model", "trivial"),))
    if res.status == "unsat" and res.multipliers is not None and check_farkas(cons, res.multipliers):
        ev = tuple((f"farkas:{i}", str(m)) for i, m in sorted(res.multipliers.items()))
        return Certificate(claim, Verdict.REFUTED, _ORACLE, ev or (("farkas", "trivial"),))
    return Certificate(claim, Verdict.UNVERIFIABLE, _ORACLE,
                       (("reason", f"no checkable witness ({res.status})"),))


def _entail_from_feasible(claim, sub) -> Certificate:
    # premises ∧ ¬concl INFEASIBLE (sub REFUTED) => entailed; FEASIBLE (VERIFIED) => counterexample.
    flip = {Verdict.REFUTED: Verdict.VERIFIED, Verdict.VERIFIED: Verdict.REFUTED}
    return Certificate(claim, flip.get(sub.verdict, Verdict.UNVERIFIABLE), _ORACLE, sub.evidence)


def check_entails(premises, conclusion) -> Certificate:
    """premises ⊨ conclusion  iff  premises ∧ ¬conclusion is infeasible. Inequality
    conclusion -> one check; '=' conclusion -> both directions composed (lattice meet)."""
    prem = list(premises)
    claim = _claim("entails " + _show(conclusion) + " from", prem)
    neg = negate(conclusion)
    if neg is not None:
        return _entail_from_feasible(claim, check_feasible(prem + [neg]))
    coeffs = {v: c for v, c in conclusion.terms}
    le = _entail_from_feasible(claim, check_feasible(prem + [constraint(coeffs, ">", conclusion.rhs)]))
    ge = _entail_from_feasible(claim, check_feasible(prem + [constraint(coeffs, "<", conclusion.rhs)]))
    meet = compose([le, ge], claim=claim)
    return Certificate(claim, meet.verdict, _ORACLE, meet.evidence)

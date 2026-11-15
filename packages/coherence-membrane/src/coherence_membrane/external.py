"""External oracles as NON-TRUSTED voices -- the seam for reach without trust.

The cross-check never trusts a single method, so an external solver (Z3, Lean) only
COUNTS when a native method corroborates it (`with_z3` adds it as one such voice).
For claims beyond the native panel's reach, `reach_validity` surfaces the external
oracle's opinion -- but ADVISORY ONLY: the system verdict stays UNVERIFIABLE and the
opinion is labeled 'uncorroborated-external'. An uncorroborated external verdict is
never elevated to a decisive VERIFIED/REFUTED. Trust-minimization, not elimination:
the trust basis is named, the verdict withheld. Nothing here imports z3 at module
load -- the adapter imports it lazily, so the core stays zero-dependency."""
from __future__ import annotations

from .certificate import Certificate, Verdict
from .crosscheck import DEFAULT_METHODS, Method
from .propositional import And, Const, Iff, Implies, Not, Or, Var, is_formula, show

_Z3 = "z3-v1"
_REACH = "reach-v1"


def z3_available() -> bool:
    try:
        import z3  # noqa: F401
        return True
    except Exception:
        return False


def _to_z3(f, z3):
    if isinstance(f, Var):
        return z3.Bool(f.name)
    if isinstance(f, Const):
        return z3.BoolVal(f.value)
    if isinstance(f, Not):
        return z3.Not(_to_z3(f.x, z3))
    if isinstance(f, And):
        return z3.And(_to_z3(f.a, z3), _to_z3(f.b, z3))
    if isinstance(f, Or):
        return z3.Or(_to_z3(f.a, z3), _to_z3(f.b, z3))
    if isinstance(f, Implies):
        return z3.Implies(_to_z3(f.a, z3), _to_z3(f.b, z3))
    if isinstance(f, Iff):
        return _to_z3(f.a, z3) == _to_z3(f.b, z3)
    raise TypeError(f"not a formula: {f!r}")


def z3_check_validity(formula, *, max_atoms: int = 16) -> Certificate:
    """Validity via Z3 (¬formula unsat). Oracle 'z3-v1' (honest provenance -- trust
    basis is z3 alone). Lazy import: absent/unknown/error/non-formula -> UNVERIFIABLE.
    max_atoms is accepted for Method-signature compatibility; z3 needs no native cap."""
    claim = show(formula) if is_formula(formula) else str(formula)
    if not is_formula(formula):
        return Certificate(claim, Verdict.UNVERIFIABLE, _Z3, (("reason", "not a formula"),))
    try:
        import z3
    except Exception:
        return Certificate(claim, Verdict.UNVERIFIABLE, _Z3, (("reason", "z3 unavailable"),))
    try:
        solver = z3.Solver()
        solver.add(z3.Not(_to_z3(formula, z3)))
        result = solver.check()
    except Exception as exc:
        return Certificate(claim, Verdict.UNVERIFIABLE, _Z3, (("error", repr(exc)),))
    if result == z3.unsat:
        return Certificate(claim, Verdict.VERIFIED, _Z3, (("valid", "negation unsatisfiable (z3)"),))
    if result == z3.sat:
        return Certificate(claim, Verdict.REFUTED, _Z3, (("invalid", "negation satisfiable (z3)"),))
    return Certificate(claim, Verdict.UNVERIFIABLE, _Z3, (("reason", f"z3 returned {result}"),))


def z3_method():
    """A Z3 Method for the cross-check panel, or None if z3 is unavailable."""
    return Method("z3", z3_check_validity) if z3_available() else None


def with_z3(methods=DEFAULT_METHODS) -> tuple:
    """The panel plus the Z3 voice if available, else unchanged. In the panel Z3 is a
    NON-TRUSTED voice: it counts only via corroboration (>=2 agree, zero dissent); an
    uncorroborated Z3 verdict does not count."""
    m = z3_method()
    return tuple(methods) + (m,) if m is not None else tuple(methods)


def reach_validity(formula, oracle: Method, *, max_atoms: int = 16) -> Certificate:
    """ADVISORY-ONLY reach for claims beyond the native panel: run the external oracle
    but return UNVERIFIABLE, carrying its opinion as labeled evidence. An uncorroborated
    external verdict is NEVER elevated to decisive -- the trust basis is named
    (advisory_oracle), the verdict withheld. max_atoms is forwarded to match the
    Method.decide(formula, *, max_atoms) contract the cross-check harness uses."""
    claim = show(formula) if is_formula(formula) else str(formula)
    if not is_formula(formula):
        return Certificate(claim, Verdict.UNVERIFIABLE, _REACH, (("reason", "not a formula"),))
    try:
        cert = oracle.decide(formula, max_atoms=max_atoms)
    except Exception as exc:
        return Certificate(claim, Verdict.UNVERIFIABLE, _REACH, (("error", f"{oracle.name}: {exc!r}"),))
    return Certificate(claim, Verdict.UNVERIFIABLE, _REACH,
                       (("assurance", "uncorroborated-external"),
                        ("advisory_oracle", cert.oracle),
                        ("advisory_verdict", cert.verdict.value),
                        ("via", oracle.name)))

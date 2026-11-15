"""Native propositional resolution refutation -- the third independent decider.

A deductive proof method, distinct in paradigm from DPLL's partial-eval SEARCH and
the truth table's total-assignment ENUMERATION: convert ¬formula to CNF and derive
the empty clause (refutation-complete for propositional unsat). Sound + complete on
the const-free fragment; a Const node, an over-cap atom count, or a CNF/closure
blow-up yields UNVERIFIABLE (fail-closed). Shares no verdict machinery with the
other deciders -- imports only the AST node types + atoms/show."""
from __future__ import annotations

from .certificate import Certificate, Verdict
from .propositional import And, Const, Iff, Implies, Not, Or, Var, atoms, show

_ORACLE = "resolution-v1"
_CLAUSE_CAP = 20000


class _Blowup(Exception):
    """CNF/resolution exceeded the clause cap -> mapped to UNVERIFIABLE."""


def _has_const(f) -> bool:
    if isinstance(f, Const):
        return True
    if isinstance(f, Var):
        return False
    if isinstance(f, Not):
        return _has_const(f.x)
    return _has_const(f.a) or _has_const(f.b)   # And/Or/Implies/Iff


def _nnf(f, neg: bool):
    """Negation normal form of f (if neg, of ¬f). Eliminates ->/<-> and pushes Not
    to literals in one pass. Input must be const-free; output is And/Or/Var/Not(Var)."""
    if isinstance(f, Var):
        return Not(f) if neg else f
    if isinstance(f, Not):
        return _nnf(f.x, not neg)
    if isinstance(f, And):
        return (Or if neg else And)(_nnf(f.a, neg), _nnf(f.b, neg))
    if isinstance(f, Or):
        return (And if neg else Or)(_nnf(f.a, neg), _nnf(f.b, neg))
    if isinstance(f, Implies):                          # a->b == ~a | b
        if neg:
            return And(_nnf(f.a, False), _nnf(f.b, True))    # ~(a->b) == a & ~b
        return Or(_nnf(f.a, True), _nnf(f.b, False))
    if isinstance(f, Iff):
        if neg:                                          # ~(a<->b) == (a & ~b) | (~a & b)
            return Or(And(_nnf(f.a, False), _nnf(f.b, True)),
                      And(_nnf(f.a, True), _nnf(f.b, False)))
        return And(Or(_nnf(f.a, True), _nnf(f.b, False)),  # a<->b == (~a|b)&(a|~b)
                   Or(_nnf(f.a, False), _nnf(f.b, True)))
    raise TypeError(f"not a formula: {f!r}")


def _clauses(f) -> set:
    """NNF formula -> set of clauses (frozenset of (name, polarity) literals)."""
    if isinstance(f, Var):
        return {frozenset({(f.name, True)})}
    if isinstance(f, Not):              # NNF: child is a Var
        return {frozenset({(f.x.name, False)})}
    if isinstance(f, And):
        cs = _clauses(f.a) | _clauses(f.b)
        if len(cs) > _CLAUSE_CAP:
            raise _Blowup()
        return cs
    if isinstance(f, Or):
        out = set()
        for c1 in _clauses(f.a):
            for c2 in _clauses(f.b):
                out.add(c1 | c2)
                if len(out) > _CLAUSE_CAP:
                    raise _Blowup()
        return out
    raise TypeError(f"unexpected NNF node: {f!r}")


def _is_taut(clause) -> bool:
    return any((name, not pol) in clause for (name, pol) in clause)


def _resolve_all(clauses) -> bool:
    """True if the empty clause is derivable (UNSAT); False if saturated (SAT)."""
    clauses = {c for c in clauses if not _is_taut(c)}
    if frozenset() in clauses:
        return True
    changed = True
    while changed:
        changed = False
        snapshot = list(clauses)
        for i in range(len(snapshot)):
            for j in range(i + 1, len(snapshot)):
                ci, cj = snapshot[i], snapshot[j]
                for name, pol in ci:
                    if (name, not pol) in cj:
                        resolvent = (ci - {(name, pol)}) | (cj - {(name, not pol)})
                        if not resolvent:
                            return True
                        rc = frozenset(resolvent)
                        if not _is_taut(rc) and rc not in clauses:
                            clauses.add(rc)
                            changed = True
                            if len(clauses) > _CLAUSE_CAP:
                                raise _Blowup()
    return False


def res_check_validity(formula, *, max_atoms: int = 16) -> Certificate:
    """Valid iff CNF(¬formula) resolves to the empty clause. VERIFIED / REFUTED /
    UNVERIFIABLE (const, over-cap, blow-up, or too deeply nested). SOUNDNESS: never
    VERIFIED unless the empty clause is derived.

    max_atoms is tighter than DPLL's (20) on purpose: CNF distribution is worst-case
    exponential in formula size, so resolution caps conservatively (fail-closed)."""
    try:
        claim = show(formula)
        if _has_const(formula):
            return Certificate(claim, Verdict.UNVERIFIABLE, _ORACLE,
                               (("reason", "Const outside resolution-v1 fragment"),))
        if len(atoms(formula)) > max_atoms:
            return Certificate(claim, Verdict.UNVERIFIABLE, _ORACLE,
                               (("reason", f"{len(atoms(formula))} atoms > cap {max_atoms}"),))
        unsat = _resolve_all(_clauses(_nnf(formula, True)))   # _nnf(.., True) = NNF(¬formula)
    except (_Blowup, RecursionError):   # a depth/size blow-up must degrade, not crash the caller
        return Certificate(type(formula).__name__, Verdict.UNVERIFIABLE, _ORACLE,
                           (("reason", "CNF/resolution blow-up or too deeply nested"),))
    if unsat:
        return Certificate(claim, Verdict.VERIFIED, _ORACLE, (("valid", "negation refuted (empty clause)"),))
    return Certificate(claim, Verdict.REFUTED, _ORACLE, (("invalid", "negation satisfiable (saturated)"),))

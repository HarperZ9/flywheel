"""Eager DPLL(T) over linear constraints -- boolean combinations of LRA atoms.

Lifts the conjunctive QF-LRA core (linarith.py) to full boolean structure. A formula
F (atoms are LinearConstraints, combined with and/or/not/implies/iff -- the
propositional nodes) is valid iff no real point satisfies ¬F. A real point induces a
boolean assignment to the atoms that (a) satisfies ¬F's propositional skeleton AND
(b) is LRA-consistent. So abstract atoms -> boolean vars, enumerate the skeleton's
satisfying assignments (truth-table, capped), and LRA-check each induced conjunction
with the proof-carrying core. Proof-carrying: VERIFIED only if every counter-branch
is Farkas-checked infeasible; REFUTED only with a check_model'd counterexample."""
from __future__ import annotations

import itertools

from .certificate import Certificate, Verdict
from .linarith import LinearConstraint, check_feasible, negate
from .propositional import And, Iff, Implies, Not, Or, Var, evaluate

_ORACLE = "lra-dpll-v1"
_ATOM_CAP = 12
_BINARY = (And, Or, Implies, Iff)


def _abstract(f, mapping):
    """Replace each distinct LinearConstraint leaf with a fresh boolean Var, returning
    a propositional formula; `mapping` accumulates {LinearConstraint: Var}."""
    if isinstance(f, LinearConstraint):
        if f not in mapping:
            mapping[f] = Var(f"a{len(mapping)}")
        return mapping[f]
    if isinstance(f, Not):
        return Not(_abstract(f.x, mapping))
    if isinstance(f, _BINARY):
        return type(f)(_abstract(f.a, mapping), _abstract(f.b, mapping))
    raise TypeError(f"not an LRA formula node: {f!r}")


def _show_con(c: LinearConstraint) -> str:
    lhs = " + ".join(f"{co}*{v}" for v, co in c.terms) or "0"
    return f"{lhs} {c.op} {c.rhs}"


def _show(f) -> str:
    if isinstance(f, LinearConstraint):
        return _show_con(f)
    if isinstance(f, Not):
        return f"~{_show(f.x)}"
    if isinstance(f, And):
        return f"({_show(f.a)} & {_show(f.b)})"
    if isinstance(f, Or):
        return f"({_show(f.a)} | {_show(f.b)})"
    if isinstance(f, Implies):
        return f"({_show(f.a)} -> {_show(f.b)})"
    if isinstance(f, Iff):
        return f"({_show(f.a)} <-> {_show(f.b)})"
    return str(f)


def check_valid(formula, *, max_atoms: int = _ATOM_CAP) -> Certificate:
    """Valid iff no real point satisfies ¬F (eager DPLL(T)). Proof-carrying:
    VERIFIED only if every counter-branch is Farkas-checked infeasible; REFUTED with a
    check_model'd counterexample; UNVERIFIABLE on cap / non-formula / false '='-atom."""
    claim = _show(formula)
    mapping: dict = {}
    try:
        prop = _abstract(formula, mapping)
    except TypeError as exc:
        return Certificate(claim, Verdict.UNVERIFIABLE, _ORACLE, (("reason", f"not an LRA formula: {exc}"),))
    rev = {var.name: con for con, var in mapping.items()}
    names = sorted(rev)
    if len(names) > max_atoms:
        return Certificate(claim, Verdict.UNVERIFIABLE, _ORACLE,
                           (("reason", f"{len(names)} atoms > cap {max_atoms}"),))
    neg = Not(prop)
    branch_verdicts = []
    for combo in itertools.product((False, True), repeat=len(names)):
        assignment = dict(zip(names, combo))
        if not evaluate(neg, assignment):
            continue                                  # boolean world not allowed by ¬F
        cons, ok = [], True
        for n in names:
            con = rev[n]
            if assignment[n]:
                cons.append(con)
            else:
                ncon = negate(con)
                if ncon is None:                      # ¬('=') is a disjunction -> can't form a conjunction
                    ok = False
                    break
                cons.append(ncon)
        if not ok:
            branch_verdicts.append(Verdict.UNVERIFIABLE)
            continue
        sub = check_feasible(cons)
        if sub.verdict is Verdict.VERIFIED:           # feasible branch = counterexample to F
            return Certificate(claim, Verdict.REFUTED, _ORACLE,
                               (("counterexample", "feasible counter-branch"),) + sub.evidence)
        branch_verdicts.append(sub.verdict)           # REFUTED (infeasible) or UNVERIFIABLE
    if all(v is Verdict.REFUTED for v in branch_verdicts):
        return Certificate(claim, Verdict.VERIFIED, _ORACLE,
                           (("valid", "every counter-branch infeasible (Farkas-checked)"),
                            ("branches", str(len(branch_verdicts)))))
    return Certificate(claim, Verdict.UNVERIFIABLE, _ORACLE,
                       (("reason", "a counter-branch was not decisively infeasible"),))

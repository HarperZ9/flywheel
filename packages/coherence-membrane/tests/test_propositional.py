from __future__ import annotations

from coherence_membrane.certificate import Verdict
from coherence_membrane.propositional import (
    And, Const, Iff, Implies, Not, Or, Var,
    atoms, evaluate, is_formula, show,
    OverCap, solve,
    check_sat, check_validity,
)


def _mp():  # modus ponens:  (A & (A -> B)) -> B
    A, B = Var("A"), Var("B")
    return Implies(And(A, Implies(A, B)), B)


def test_atoms_and_is_formula():
    assert atoms(_mp()) == {"A", "B"}
    assert is_formula(_mp()) is True
    assert is_formula("A & B") is False
    assert atoms(Const(True)) == set()


def test_evaluate_truth_table():
    # modus ponens is true under every assignment
    for a in (True, False):
        for b in (True, False):
            assert evaluate(_mp(), {"A": a, "B": b}) is True
    # A -> B is false only at A=1,B=0
    f = Implies(Var("A"), Var("B"))
    assert evaluate(f, {"A": True, "B": False}) is False
    assert evaluate(f, {"A": False, "B": False}) is True


def test_show_is_deterministic():
    assert show(_mp()) == "((A & (A -> B)) -> B)"
    assert show(Not(Var("A"))) == "~A"
    assert show(Const(True)) == "T"


def test_solve_sat_unsat():
    A, B = Var("A"), Var("B")
    # satisfiable: A & ~B  -> model A=1,B=0
    m = solve(And(A, Not(B)))
    assert m == {"A": True, "B": False}
    # unsatisfiable: A & ~A -> None
    assert solve(And(A, Not(A))) is None
    # negation of a tautology is unsat
    assert solve(Not(Or(A, Not(A)))) is None


def test_solve_over_cap():
    import pytest
    f = Or(Or(Var("A"), Var("B")), Var("C"))   # 3 atoms
    with pytest.raises(OverCap):
        solve(f, max_atoms=2)


def test_check_validity_verified_and_refuted():
    A, B = Var("A"), Var("B")
    mp = Implies(And(A, Implies(A, B)), B)
    c = check_validity(mp)
    assert c.verdict is Verdict.VERIFIED and c.oracle == "propositional-dpll-v1"
    # A -> B is not valid; counterexample A=1, B=0
    c2 = check_validity(Implies(A, B))
    assert c2.verdict is Verdict.REFUTED
    assert dict(c2.evidence) == {"counterexample:A": "1", "counterexample:B": "0"}


def test_check_sat_and_excluded_middle():
    A = Var("A")
    assert check_sat(And(A, Not(A))).verdict is Verdict.REFUTED      # unsat
    assert check_validity(Or(A, Not(A))).verdict is Verdict.VERIFIED  # tautology


def test_over_cap_is_unverifiable_then_backend():
    A, B, C = Var("A"), Var("B"), Var("C")
    f = Or(Or(A, B), C)                       # 3 atoms
    c = check_validity(f, max_atoms=2)
    assert c.verdict is Verdict.UNVERIFIABLE   # native gave up, no backend
    # optional-oracle seam: a backend callable is consulted on over-cap
    from coherence_membrane.certificate import Certificate
    sentinel = Certificate("backend", Verdict.VERIFIED, "fake-backend-v0")
    c2 = check_validity(f, max_atoms=2, backend=lambda _f: sentinel)
    assert c2 is sentinel

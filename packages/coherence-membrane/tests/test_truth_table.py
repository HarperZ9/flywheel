from __future__ import annotations

import random

from coherence_membrane.certificate import Verdict
from coherence_membrane.propositional import (
    And, Iff, Implies, Not, Or, Var, check_validity,
)
from coherence_membrane.truth_table import tt_check_sat, tt_check_validity


def _mp():
    A, B = Var("A"), Var("B")
    return Implies(And(A, Implies(A, B)), B)


def test_tt_validity_and_sat():
    A, B = Var("A"), Var("B")
    assert tt_check_validity(_mp()).verdict is Verdict.VERIFIED           # tautology
    assert tt_check_validity(Or(A, Not(A))).verdict is Verdict.VERIFIED   # excluded middle
    c = tt_check_validity(Implies(A, B))                                  # not valid
    assert c.verdict is Verdict.REFUTED
    assert dict(c.evidence) == {"counterexample:A": "1", "counterexample:B": "0"}
    assert c.oracle == "truth-table-v1"
    assert tt_check_sat(And(A, Not(A))).verdict is Verdict.REFUTED        # unsat


def test_tt_over_cap_is_unverifiable():
    f = Or(Or(Var("A"), Var("B")), Var("C"))                              # 3 atoms
    assert tt_check_validity(f, max_atoms=2).verdict is Verdict.UNVERIFIABLE


def test_tt_agrees_with_dpll_on_random_formulas():
    # the two INDEPENDENT deciders must never disagree on a real formula
    rng = random.Random(20260620)
    names = ["A", "B", "C", "D"]
    ops = {"and": And, "or": Or, "impl": Implies, "iff": Iff}

    def rand(depth):
        if depth == 0 or rng.random() < 0.3:
            return Var(rng.choice(names))
        kind = rng.choice(["not", "and", "or", "impl", "iff"])
        if kind == "not":
            return Not(rand(depth - 1))
        return ops[kind](rand(depth - 1), rand(depth - 1))

    for _ in range(500):
        f = rand(4)
        assert tt_check_validity(f).verdict is check_validity(f).verdict

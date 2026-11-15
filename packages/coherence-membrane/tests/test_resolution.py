from __future__ import annotations

import random

from coherence_membrane.certificate import Verdict
from coherence_membrane.propositional import (
    And, Const, Iff, Implies, Not, Or, Var, check_validity,
)
from coherence_membrane.resolution import res_check_validity
from coherence_membrane.truth_table import tt_check_validity


def _mp():
    A, B = Var("A"), Var("B")
    return Implies(And(A, Implies(A, B)), B)


def test_resolution_validity():
    A, B = Var("A"), Var("B")
    assert res_check_validity(_mp()).verdict is Verdict.VERIFIED           # modus ponens
    assert res_check_validity(Or(A, Not(A))).verdict is Verdict.VERIFIED   # excluded middle
    assert res_check_validity(Iff(A, A)).verdict is Verdict.VERIFIED       # A <-> A
    assert res_check_validity(Implies(A, B)).verdict is Verdict.REFUTED    # not valid
    assert res_check_validity(And(A, Not(A))).verdict is Verdict.REFUTED   # contradiction not valid
    assert res_check_validity(_mp()).oracle == "resolution-v1"


def test_resolution_over_cap_is_unverifiable():
    f = Or(Or(Var("A"), Var("B")), Var("C"))                               # 3 atoms
    assert res_check_validity(f, max_atoms=2).verdict is Verdict.UNVERIFIABLE


def test_resolution_const_is_unverifiable():
    # Const is outside resolution-v1's fragment -> fail-closed (the panel still decides)
    assert res_check_validity(Or(Var("A"), Const(True))).verdict is Verdict.UNVERIFIABLE


def test_resolution_deeply_nested_degrades():
    # a pathologically deep formula must degrade to UNVERIFIABLE, not raise (fail-closed)
    f = Var("A")
    for _ in range(2000):
        f = Not(f)
    assert res_check_validity(f).verdict is Verdict.UNVERIFIABLE


def test_resolution_agrees_or_abstains_vs_dpll_and_truth_table():
    # three INDEPENDENT paradigms: resolution must AGREE when decisive, or abstain
    # (UNVERIFIABLE on CNF blow-up) -- never disagree
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
        v = res_check_validity(f).verdict
        if v is Verdict.UNVERIFIABLE:
            continue                      # abstained (blow-up) -- the other two still decide
        assert v is check_validity(f).verdict
        assert v is tt_check_validity(f).verdict

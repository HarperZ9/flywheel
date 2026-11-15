from __future__ import annotations

from fractions import Fraction

from coherence_membrane.linarith import LinearConstraint, constraint, negate


def test_constraint_normalizes_ge_gt():
    c = constraint({"x": 1}, ">=", 3)          # x >= 3  ->  -x <= -3
    assert c.op == "<=" and c.coeff("x") == Fraction(-1) and c.rhs == Fraction(-3)
    g = constraint({"x": 2}, ">", 1)           # 2x > 1  ->  -2x < -1
    assert g.op == "<" and g.coeff("x") == Fraction(-2) and g.rhs == Fraction(-1)


def test_constraint_drops_zero_and_sorts():
    c = constraint({"y": 0, "b": 1, "a": 2}, "<=", 5)
    assert c.terms == (("a", Fraction(2)), ("b", Fraction(1)))
    assert c.variables == ("a", "b")


def test_evaluate():
    c = constraint({"x": 1, "y": 1}, "<=", 5)
    assert c.evaluate({"x": 2, "y": 3}) is True
    assert c.evaluate({"x": 4, "y": 3}) is False
    assert constraint({"x": 1}, "=", 2).evaluate({"x": 2}) is True
    assert constraint({"x": 1}, "<", 2).evaluate({"x": 2}) is False


def test_negate():
    assert negate(constraint({"x": 1}, "<=", 3)).op == "<"   # ¬(x<=3) is (x>3) -> -x < -3
    assert negate(constraint({"x": 1}, "<=", 3)).coeff("x") == Fraction(-1)
    assert negate(constraint({"x": 1}, "<", 3)).op == "<="   # ¬(x<3) is (x>=3) -> -x <= -3
    assert negate(constraint({"x": 1}, "=", 3)) is None      # disjunction


from coherence_membrane.linarith import fourier_motzkin


def test_fm_feasible_returns_checkable_model():
    cons = [constraint({"x": 1}, ">=", 0), constraint({"y": 1}, ">=", 0),
            constraint({"x": 1, "y": 1}, "<=", 10)]
    res = fourier_motzkin(cons)
    assert res.status == "sat"
    assert all(c.evaluate(res.model) for c in cons)   # the model really satisfies them


def test_fm_infeasible_returns_farkas_multipliers():
    cons = [constraint({"x": 1}, ">=", 1), constraint({"x": 1}, "<=", 0)]   # x>=1 and x<=0
    res = fourier_motzkin(cons)
    assert res.status == "unsat"
    assert res.multipliers is not None and any(m != 0 for m in res.multipliers.values())


def test_fm_equality_infeasible():
    cons = [constraint({"x": 1, "y": 1}, "=", 0), constraint({"x": 1, "y": 1}, "=", 1)]
    assert fourier_motzkin(cons).status == "unsat"


def test_fm_strict_contradiction():
    cons = [constraint({"x": 1}, "<", 0), constraint({"x": 1}, ">", 0)]   # x<0 and x>0
    assert fourier_motzkin(cons).status == "unsat"


from coherence_membrane.certificate import Verdict
from coherence_membrane.linarith import check_entails, check_farkas, check_feasible, check_model


def test_check_feasible_verified_and_refuted():
    feas = [constraint({"x": 1}, ">=", 0), constraint({"x": 1}, "<=", 5)]
    assert check_feasible(feas).verdict is Verdict.VERIFIED
    infeas = [constraint({"x": 1}, ">=", 1), constraint({"x": 1}, "<=", 0)]
    assert check_feasible(infeas).verdict is Verdict.REFUTED


def test_check_entails_classic():
    # {x>=0, y>=0} entails x+y>=0
    prem = [constraint({"x": 1}, ">=", 0), constraint({"y": 1}, ">=", 0)]
    assert check_entails(prem, constraint({"x": 1, "y": 1}, ">=", 0)).verdict is Verdict.VERIFIED
    # {x>=0, y>=0} does NOT entail x+y>=1 (counterexample x=y=0)
    assert check_entails(prem, constraint({"x": 1, "y": 1}, ">=", 1)).verdict is Verdict.REFUTED


def test_check_entails_equality():
    # {x=2, y=3} entails x+y=5
    prem = [constraint({"x": 1}, "=", 2), constraint({"y": 1}, "=", 3)]
    assert check_entails(prem, constraint({"x": 1, "y": 1}, "=", 5)).verdict is Verdict.VERIFIED
    assert check_entails(prem, constraint({"x": 1, "y": 1}, "=", 6)).verdict is Verdict.REFUTED


def test_checker_rejects_tampered_farkas():
    # the checker is the trusted base: a bogus multiplier set must NOT validate
    infeas = [constraint({"x": 1}, ">=", 1), constraint({"x": 1}, "<=", 0)]
    assert check_farkas(infeas, {0: Fraction(1), 1: Fraction(1)}) is True            # the genuine certificate validates
    assert check_farkas(infeas, {0: Fraction(0), 1: Fraction(0)}) is False          # trivial: no contradiction
    assert check_model(infeas, {"x": Fraction(5)}) is False                          # x=5 violates x<=0

from __future__ import annotations

from coherence_membrane.certificate import Verdict
from coherence_membrane.linarith import constraint
from coherence_membrane.lra_dpll import check_valid
from coherence_membrane.propositional import And, Implies, Or


def test_valid_boolean_lra():
    f = Implies(constraint({"x": 1}, ">", 0), constraint({"x": 1}, ">=", 0))      # x>0 -> x>=0
    assert check_valid(f).verdict is Verdict.VERIFIED
    g = Implies(And(constraint({"x": 1}, ">=", 0), constraint({"y": 1}, ">=", 0)),
                constraint({"x": 1, "y": 1}, ">=", 0))                            # x,y>=0 -> x+y>=0
    assert check_valid(g).verdict is Verdict.VERIFIED
    assert check_valid(g).oracle == "lra-dpll-v1"


def test_disjunction_excluded_middle_over_reals():
    f = Or(constraint({"x": 1}, "<", 0), constraint({"x": 1}, ">=", 0))           # x<0 | x>=0
    assert check_valid(f).verdict is Verdict.VERIFIED


def test_invalid_has_counterexample():
    f = Implies(constraint({"x": 1}, ">=", 0), constraint({"x": 1}, ">=", 1))     # x>=0 -> x>=1 (x=0 cex)
    assert check_valid(f).verdict is Verdict.REFUTED


def test_agrees_with_entailment_path():
    # check_valid(Implies(p, c)) must equal check_entails([p], c) for inequality atoms
    from coherence_membrane.linarith import check_entails
    p = constraint({"x": 1, "y": 1}, "<=", 4)
    c = constraint({"x": 1}, "<=", 4)
    assert check_valid(Implies(p, c)).verdict is check_entails([p], c).verdict


def test_over_atom_cap_unverifiable():
    atoms = [constraint({f"x{i}": 1}, ">=", 0) for i in range(8)]
    f = atoms[0]
    for a in atoms[1:]:
        f = And(f, a)
    assert check_valid(f, max_atoms=4).verdict is Verdict.UNVERIFIABLE


def test_equality_atom_false_branch_degrades():
    # an '=' atom whose negation is needed (disjunction) -> UNVERIFIABLE, never a wrong verdict
    f = constraint({"x": 1}, "=", 0)            # a bare '=' atom is not valid; ¬ is a disjunction
    assert check_valid(f).verdict is Verdict.UNVERIFIABLE

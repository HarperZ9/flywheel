from __future__ import annotations

import sys

import pytest

from coherence_membrane.certificate import Certificate, Verdict
from coherence_membrane.crosscheck import DEFAULT_METHODS, Method
from coherence_membrane.external import (
    reach_validity, with_z3, z3_available, z3_check_validity, z3_method,
)
from coherence_membrane.propositional import And, Implies, Var, show


def _mp():
    A, B = Var("A"), Var("B")
    return Implies(And(A, Implies(A, B)), B)


def test_no_core_z3_import():
    # importing the package (and external) must NOT import z3 -- the adapter is lazy
    import coherence_membrane            # noqa: F401
    import coherence_membrane.external   # noqa: F401
    assert "z3" not in sys.modules


def test_z3_available_is_bool():
    assert isinstance(z3_available(), bool)


def test_with_z3_unchanged_when_absent():
    if z3_available():
        pytest.skip("z3 installed; absence behavior not applicable")
    assert with_z3(DEFAULT_METHODS) == DEFAULT_METHODS    # no z3 -> panel unchanged
    assert z3_method() is None


def test_z3_check_validity_unverifiable_when_absent():
    if z3_available():
        pytest.skip("z3 installed")
    c = z3_check_validity(_mp())
    assert c.verdict is Verdict.UNVERIFIABLE
    assert c.oracle == "z3-v1"


def test_reach_is_advisory_only_on_verified_opinion():
    # an external oracle that says VERIFIED -> system stays UNVERIFIABLE, opinion labeled
    yes = Method("mock", lambda f, *, max_atoms=16: Certificate(show(f), Verdict.VERIFIED, "mock-v0", (("m", "1"),)))
    c = reach_validity(_mp(), yes)
    assert c.verdict is Verdict.UNVERIFIABLE              # never elevated
    assert c.oracle == "reach-v1"
    ev = dict(c.evidence)
    assert ev["advisory_verdict"] == "verified"
    assert ev["assurance"] == "uncorroborated-external"
    assert ev["advisory_oracle"] == "mock-v0"


def test_reach_is_advisory_only_on_refuted_opinion():
    no = Method("mock", lambda f, *, max_atoms=16: Certificate(show(f), Verdict.REFUTED, "mock-v0"))
    c = reach_validity(_mp(), no)
    assert c.verdict is Verdict.UNVERIFIABLE
    assert dict(c.evidence)["advisory_verdict"] == "refuted"


def test_reach_failclosed_on_raise_and_foreign():
    boom = Method("boom", lambda f, *, max_atoms=16: (_ for _ in ()).throw(RuntimeError("x")))
    assert reach_validity(_mp(), boom).verdict is Verdict.UNVERIFIABLE      # raising oracle captured
    assert reach_validity("not a formula", boom).verdict is Verdict.UNVERIFIABLE


def test_reach_forwards_max_atoms_to_oracle():
    # an oracle with REQUIRED max_atoms (no default) must still work via reach -- the
    # reach path forwards max_atoms to match the Method.decide(formula, *, max_atoms) contract
    def strict(f, *, max_atoms):   # no default: would TypeError if reach omitted max_atoms
        return Certificate(show(f), Verdict.VERIFIED, "strict-v0")
    c = reach_validity(_mp(), Method("strict", strict))
    assert c.verdict is Verdict.UNVERIFIABLE
    assert dict(c.evidence)["advisory_verdict"] == "verified"   # i.e. it ran without TypeError


@pytest.mark.skipif(not z3_available(), reason="z3 not installed")
def test_z3_decide_agrees_with_native_panel_when_present():
    from coherence_membrane.crosscheck import cross_check_validity
    from coherence_membrane.propositional import Not, Or
    m = z3_method()
    for f in (_mp(), Implies(Var("A"), Var("B")), Or(Var("A"), Not(Var("A")))):
        assert m.decide(f).verdict is cross_check_validity(f).verdict

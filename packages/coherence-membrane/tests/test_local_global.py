from __future__ import annotations

from coherence_membrane.certificate import Certificate, Verdict
from coherence_membrane.local_global import cross_check_local


def _local(verdict, oracle="locus"):
    """A synthetic per-locus Certificate (no real number theory needed)."""
    return Certificate("locus claim", verdict, oracle)


def _in_class_witness(_loci):
    """A WITNESSED in-class class-membership criterion: returns a VERIFIED Certificate
    attesting the claim lies in a proven completeness class (e.g. genus-0 conics)."""
    return Certificate("in completeness class", Verdict.VERIFIED, "class-witness-v1")


def _out_of_class_witness(_loci):
    """A WITNESSED out-of-class criterion: returns a REFUTED Certificate (positive proof
    the claim lies OUTSIDE a proven completeness class -- e.g. Selmer's cubic)."""
    return Certificate("in completeness class", Verdict.REFUTED, "class-witness-v1")


def test_genus0_in_class_lifts_to_verified():
    # the Hasse principle HOLDS here (quadratic-form / genus-0 conic): unanimous locals
    # + a WITNESSED in-class certificate -> the global property is VERIFIED.
    locals_ = [_local(Verdict.VERIFIED), _local(Verdict.VERIFIED), _local(Verdict.VERIFIED)]
    c = cross_check_local("conic has a rational point", locals_,
                          in_completeness_class=_in_class_witness)
    assert c.verdict is Verdict.VERIFIED
    assert c.oracle == "cross-check-local-v1"
    ev = dict(c.evidence)
    assert ev["in_completeness_class"] == "true"
    assert ev["class_witness"] == "certificate"   # lifted only on a witnessed certificate
    # the loci are carried in the proof
    assert ev["locus0:locus"] == "verified"


def test_selmer_style_out_of_class_is_unverifiable():
    # THE headline soundness test. Selmer's cubic 3x^3+4y^3+5z^3=0 is solvable in every
    # local field yet has no global rational solution: unanimous locals OUTSIDE a proven
    # completeness class must NEVER lift to VERIFIED -- it downgrades to UNVERIFIABLE.
    # The out-of-class status is itself WITNESSED (a REFUTED class certificate).
    locals_ = [_local(Verdict.VERIFIED), _local(Verdict.VERIFIED), _local(Verdict.VERIFIED)]
    c = cross_check_local("cubic has a rational point", locals_,
                          in_completeness_class=_out_of_class_witness)
    assert c.verdict is Verdict.UNVERIFIABLE
    reason = dict(c.evidence)["reason"]
    assert "local-global" in reason and "Hasse" in reason
    # and it is decidedly NOT a false VERIFIED
    assert c.verdict is not Verdict.VERIFIED


def test_single_local_refuted_refutes_global():
    # the sound direction: ONE local obstruction kills the global property, even with a
    # witnessed in-class certificate (a real obstruction beats the lifting guard).
    locals_ = [_local(Verdict.VERIFIED), _local(Verdict.REFUTED, "bad-prime"), _local(Verdict.VERIFIED)]
    c = cross_check_local("has a global point", locals_, in_completeness_class=_in_class_witness)
    assert c.verdict is Verdict.REFUTED


def test_unknown_class_predicate_is_unverifiable():
    # class certificate absent/unknown -> fail-closed UNVERIFIABLE (soundness over
    # completeness), with the Hasse reason; never VERIFIED on unanimous-local alone.
    locals_ = [_local(Verdict.VERIFIED), _local(Verdict.VERIFIED)]
    c = cross_check_local("claim", locals_, in_completeness_class=None)
    assert c.verdict is Verdict.UNVERIFIABLE
    ev = dict(c.evidence)
    assert ev["in_completeness_class"] == "unknown"
    assert "Hasse" in ev["reason"]


def test_raising_class_predicate_fails_closed():
    # a class predicate that RAISES must not crash the combinator and must not pass the
    # guard -> UNVERIFIABLE (TOTAL + fail-closed), treated as unknown.
    def boom(_loci):
        raise RuntimeError("class oracle exploded")

    locals_ = [_local(Verdict.VERIFIED), _local(Verdict.VERIFIED)]
    c = cross_check_local("claim", locals_, in_completeness_class=boom)
    assert c.verdict is Verdict.UNVERIFIABLE
    assert "Hasse" in dict(c.evidence)["reason"]


def test_callable_class_predicate_in_class_verifies():
    # the injected criterion is a predicate over the loci returning a witnessed Certificate
    # (mirrors distance/deviation injection): a VERIFIED-returning predicate + unanimous
    # locals -> VERIFIED.
    locals_ = [_local(Verdict.VERIFIED), _local(Verdict.VERIFIED)]
    c = cross_check_local(
        "claim", locals_,
        in_completeness_class=lambda loci: Certificate(
            "membership", Verdict.VERIFIED if len(loci) == 2 else Verdict.REFUTED, "class-v1"),
    )
    assert c.verdict is Verdict.VERIFIED
    assert dict(c.evidence)["in_completeness_class"] == "true"


def test_bare_bool_true_is_asserted_not_witnessed():
    # THE Hasse-seam closure: a bare True is membership ASSERTED, not WITNESSED -- it must
    # NEVER lift unanimous-local to VERIFIED (same root seam as reconcile's independence).
    locals_ = [_local(Verdict.VERIFIED), _local(Verdict.VERIFIED)]
    c = cross_check_local("claim", locals_, in_completeness_class=True)
    assert c.verdict is Verdict.UNVERIFIABLE
    ev = dict(c.evidence)
    assert ev["in_completeness_class"] == "asserted"
    assert ev["reason"] == "class membership asserted, not witnessed"


def test_callable_returning_bare_bool_is_asserted():
    # a callable that returns a bare bool is ALSO only an assertion, not a witness ->
    # UNVERIFIABLE (no Certificate => nothing witnessed).
    locals_ = [_local(Verdict.VERIFIED), _local(Verdict.VERIFIED)]
    c = cross_check_local("claim", locals_, in_completeness_class=lambda loci: len(loci) == 2)
    assert c.verdict is Verdict.UNVERIFIABLE
    assert dict(c.evidence)["in_completeness_class"] == "asserted"


def test_unverifiable_class_certificate_does_not_lift():
    # an UNVERIFIABLE class certificate witnesses neither in- nor out-of-class -> unknown,
    # fail-closed to UNVERIFIABLE with the Hasse reason (never VERIFIED).
    locals_ = [_local(Verdict.VERIFIED), _local(Verdict.VERIFIED)]
    c = cross_check_local(
        "claim", locals_,
        in_completeness_class=lambda loci: Certificate("m", Verdict.UNVERIFIABLE, "class-v1"))
    assert c.verdict is Verdict.UNVERIFIABLE
    ev = dict(c.evidence)
    assert ev["in_completeness_class"] == "unknown"
    assert "Hasse" in ev["reason"]


def test_local_unverifiable_attenuates():
    # a single inconclusive locus means the decomposition is not unanimously decisive ->
    # UNVERIFIABLE via the proven meet, even inside the completeness class.
    locals_ = [_local(Verdict.VERIFIED), _local(Verdict.UNVERIFIABLE)]
    c = cross_check_local("claim", locals_, in_completeness_class=True)
    assert c.verdict is Verdict.UNVERIFIABLE
    # this is the lattice-attenuation path, NOT the Hasse-guard path
    assert dict(c.evidence)["reason"] == "locals not unanimously decisive"


def test_empty_decomposition_is_unverifiable():
    # fail-closed: an empty decomposition lifted nothing (NOT vacuous VERIFIED).
    c = cross_check_local("claim", [], in_completeness_class=True)
    assert c.verdict is Verdict.UNVERIFIABLE
    assert dict(c.evidence)["reason"] == "no local results to combine"


def test_non_certificate_local_is_unverifiable():
    # a malformed local (not a Certificate) makes the decomposition uninterpretable ->
    # UNVERIFIABLE (TOTAL), never an exception.
    c = cross_check_local("claim", [_local(Verdict.VERIFIED), "not a cert"], in_completeness_class=True)
    assert c.verdict is Verdict.UNVERIFIABLE
    assert dict(c.evidence)["reason"] == "a local result is not a Certificate"


def test_non_iterable_local_results_is_unverifiable():
    # local_results that cannot even be iterated -> UNVERIFIABLE (TOTAL).
    c = cross_check_local("claim", 123, in_completeness_class=True)
    assert c.verdict is Verdict.UNVERIFIABLE
    assert dict(c.evidence)["reason"] == "local results not iterable"


def test_deterministic_same_inputs_same_certificate():
    # determinism: identical inputs yield an identical Certificate every call.
    def build():
        locals_ = [_local(Verdict.VERIFIED), _local(Verdict.VERIFIED), _local(Verdict.VERIFIED)]
        return cross_check_local("c", locals_, in_completeness_class=False)

    a, b = build(), build()
    assert a == b
    assert a.verdict is b.verdict and a.evidence == b.evidence and a.oracle == b.oracle


def test_never_raises_is_total():
    # TOTAL contract: even a pathological in_completeness_class object cannot make the
    # combinator raise. A non-bool, non-callable flag is treated as unknown -> UNVERIFIABLE.
    locals_ = [_local(Verdict.VERIFIED)]
    c = cross_check_local("c", locals_, in_completeness_class=object())
    assert c.verdict is Verdict.UNVERIFIABLE
    assert dict(c.evidence)["in_completeness_class"] == "unknown"

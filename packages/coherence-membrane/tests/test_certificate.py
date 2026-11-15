from __future__ import annotations

from coherence_membrane.certificate import Certificate, Verdict


def test_verdict_values():
    assert {v.value for v in Verdict} == {"verified", "refuted", "unverifiable"}


def test_certificate_construct_and_to_dict():
    c = Certificate("(A -> A)", Verdict.VERIFIED, "propositional-dpll-v1", (("valid", "negation unsatisfiable"),))
    assert c.verdict is Verdict.VERIFIED
    assert c.oracle == "propositional-dpll-v1"
    assert c.to_dict() == {
        "claim": "(A -> A)",
        "verdict": "verified",
        "oracle": "propositional-dpll-v1",
        "evidence": [["valid", "negation unsatisfiable"]],
    }


def test_certificate_is_frozen_and_default_evidence():
    import pytest
    c = Certificate("x", Verdict.UNVERIFIABLE, "o")
    assert c.evidence == ()
    with pytest.raises(AttributeError):
        c.verdict = Verdict.VERIFIED


def test_certificate_from_dict_round_trips():
    c = Certificate("(A -> A)", Verdict.VERIFIED, "propositional-dpll-v1",
                    (("valid", "negation unsatisfiable"),))
    assert Certificate.from_dict(c.to_dict()) == c           # to_dict / from_dict are symmetric
    e = Certificate("x", Verdict.UNVERIFIABLE, "o")          # default (empty) evidence
    assert Certificate.from_dict(e.to_dict()) == e
    assert Certificate.from_dict(e.to_dict()).evidence == ()
    got = Certificate.from_dict({"claim": "c", "verdict": "refuted", "oracle": "o", "evidence": []})
    assert got.verdict is Verdict.REFUTED                    # verdict string -> enum


def test_certificate_from_dict_rejects_unknown_verdict():
    import pytest
    with pytest.raises(ValueError):
        Certificate.from_dict({"claim": "c", "verdict": "trusted", "oracle": "o", "evidence": []})

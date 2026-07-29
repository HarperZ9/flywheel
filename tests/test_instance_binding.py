"""The certificate must answer the instance it was given.

`CertificateOracle.verify` took a `task` argument and never read it.
`declared_parameters` reads the CERTIFICATE, so a candidate declared its own
instance: asked for a 64x64 problem it could submit a valid 3x3 certificate and
earn PASS. Four different instances produced byte-identical verdicts and
byte-identical output hashes.

The fix is not "always require a task". It is that an UNBOUND verdict must say it
is unbound, because the honest reading of a certificate checked against no
instance is "internally valid, and I cannot tell you whether it answers anything".
"""
import json

import pytest

from harness.certificates.independent import IndependentZarankiewiczOracle
from harness.certificates.zarankiewicz import ZarankiewiczOracle

# A star is K_{2,2}-free for any size, so this is a genuinely VALID certificate.
STAR_3x3 = json.dumps({"m": 3, "n": 3, "s": 2, "t": 2,
                       "edges": [[0, 0], [0, 1], [0, 2], [1, 0], [2, 0]],
                       "edge_count": 5})
ASKED_3x3 = {"m": 3, "n": 3, "s": 2, "t": 2}
ASKED_64 = {"m": 64, "n": 64, "s": 2, "t": 2}
ASKED_K33 = {"m": 3, "n": 3, "s": 3, "t": 3}


@pytest.fixture(params=[ZarankiewiczOracle, IndependentZarankiewiczOracle])
def oracle(request):
    """Both checkers must bind. A held-out checker that ignores the instance
    would agree with the primary for the wrong reason."""
    return request.param()


def test_a_matching_instance_passes(oracle):
    r = oracle.verify(STAR_3x3, ASKED_3x3)
    assert r.verdict() == "PASS"
    assert r.coverage["instance_bound"] is True
    assert r.coverage["instance_binding"] == ASKED_3x3


def test_a_valid_certificate_for_the_wrong_size_now_fails(oracle):
    """The false accept this whole change exists to close."""
    r = oracle.verify(STAR_3x3, ASKED_64)
    assert r.verdict() == "FAIL"
    assert "does not answer the instance" in r.stdout_excerpt
    assert '"m":{"asked":64,"declared":3}' in r.stdout_excerpt


def test_a_valid_certificate_for_the_wrong_forbidden_subgraph_fails(oracle):
    """Same shape, different question. K_{3,3}-free is not K_{2,2}-free."""
    r = oracle.verify(STAR_3x3, ASKED_K33)
    assert r.verdict() == "FAIL"
    assert '"s":{"asked":3,"declared":2}' in r.stdout_excerpt


def test_answering_the_wrong_question_is_the_candidate_s_error(oracle):
    """FAIL, not UNVERIFIABLE. A certificate for another instance is a wrong
    answer, not a gap in the record, and the attribution must say so."""
    r = oracle.verify(STAR_3x3, ASKED_64)
    assert r.attribution == "CANDIDATE"


def test_an_unbound_verdict_says_it_is_unbound(oracle):
    r = oracle.verify(STAR_3x3, None)
    assert r.verdict() == "PASS"
    assert r.coverage["instance_bound"] is False
    assert "NOT_PROVES_ANSWERS_THE_QUESTION_ASKED" in r.does_not_prove


def test_a_bound_verdict_does_not_carry_the_unbound_disclaimer(oracle):
    r = oracle.verify(STAR_3x3, ASKED_3x3)
    assert "NOT_PROVES_ANSWERS_THE_QUESTION_ASKED" not in r.does_not_prove


def test_the_digest_distinguishes_the_instance(oracle):
    """Before the fix these four were byte-identical, which meant a receipt
    could not tell a stranger which question had been answered."""
    digests = {label: oracle.verify(STAR_3x3, t).output_hash
               for label, t in (("unbound", None), ("3x3", ASKED_3x3),
                                ("64x64", ASKED_64), ("k33", ASKED_K33))}
    assert len(set(digests.values())) == 4, digests


def test_a_task_that_is_not_a_dict_is_unbound_rather_than_crashing(oracle):
    for junk in ("a string", 42, ["a", "list"], object()):
        r = oracle.verify(STAR_3x3, junk)
        assert r.coverage["instance_bound"] is False


def test_a_task_missing_the_binding_keys_is_unbound(oracle):
    """A task carrying only bookkeeping binds nothing, and must not silently
    read as bound."""
    r = oracle.verify(STAR_3x3, {"task_id": "abc", "difficulty": 3})
    assert r.coverage["instance_bound"] is False
    assert "NOT_PROVES_ANSWERS_THE_QUESTION_ASKED" in r.does_not_prove


def test_a_partially_binding_task_binds_what_it_names(oracle):
    """m alone is a real constraint even without n."""
    assert oracle.verify(STAR_3x3, {"m": 3}).verdict() == "PASS"
    assert oracle.verify(STAR_3x3, {"m": 64}).verdict() == "FAIL"


def test_both_checkers_agree_on_a_bound_instance():
    """The held-out checker must reach the same verdict for the same reason."""
    a, b = ZarankiewiczOracle(), IndependentZarankiewiczOracle()
    for task in (ASKED_3x3, ASKED_64, ASKED_K33, None):
        assert a.verify(STAR_3x3, task).verdict() == b.verify(STAR_3x3, task).verdict()


def test_a_family_with_no_declared_binding_is_never_silently_bound():
    """binding_keys defaults to empty, so a new family is unbound and says so
    rather than inheriting a binding it never declared."""
    from harness.certificates.base import CertificateOracle
    assert CertificateOracle.binding_keys == ()
    assert CertificateOracle().instance_binding({"m": 3, "n": 3}) is None

"""The envelope carries TWO digests, and conflating them is the defect.

The subject digest (content_hash / content_sha256) answers "what was checked".
It is verdict-free on purpose: it is the in-toto subject id, and two verifiers
who reach OPPOSITE conclusions about the same task and candidate must still
produce the same subject id or their disagreement cannot be located.

The claim digest (claim_hash / claim_sha256) answers "what was concluded". It
binds the verdict and the oracle output hash, so editing a stored FAIL to PASS
changes it. That is the value a signature must cover.

Before this split there was only the subject digest, so nothing at the envelope
level changed when a verdict was flipped.
"""
import dataclasses

from harness.envelope import ProofEnvelope


def _env(verdict="PASS", out_hash="abc"):
    return ProofEnvelope(
        task_id="t1", candidate="def f(): pass", oracle="pytest",
        oracle_cmd="pytest -q", oracle_output_hash=out_hash, verdict=verdict,
        model_ref="m", seed=1, prompt_hash="p", budget_spent={})


def test_flipping_the_verdict_changes_the_claim_digest():
    a = _env(verdict="FAIL")
    b = dataclasses.replace(a, verdict="PASS")
    assert a.claim_hash() != b.claim_hash()
    assert a.claim_sha256() != b.claim_sha256()


def test_changing_the_oracle_output_hash_changes_the_claim_digest():
    a = _env(out_hash="abc")
    b = dataclasses.replace(a, oracle_output_hash="def")
    assert a.claim_hash() != b.claim_hash()


def test_the_subject_digest_stays_verdict_free_so_disagreement_is_comparable():
    # Two verifiers, opposite conclusions, same subject. This is the property
    # the in-toto export depends on and must not be broken.
    a = _env(verdict="PASS", out_hash="abc")
    b = _env(verdict="FAIL", out_hash="totally-different")
    assert a.content_hash() == b.content_hash()
    assert a.content_sha256() == b.content_sha256()


def test_the_volatile_excerpt_affects_neither_digest():
    a = _env()
    b = dataclasses.replace(a, oracle_stdout_excerpt="1 passed in 0.31s")
    assert a.content_hash() == b.content_hash()
    assert a.claim_hash() == b.claim_hash()


def test_identical_envelopes_hash_identically_under_both_digests():
    assert _env().content_hash() == _env().content_hash()
    assert _env().claim_sha256() == _env().claim_sha256()


def test_claim_digest_is_tagged_64_hex_and_the_short_id_is_its_prefix():
    e = _env()
    tag, hexd = e.claim_sha256().split(":", 1)
    assert tag == "sha256"
    assert len(hexd) == 64
    assert hexd.startswith(e.claim_hash())


def test_the_two_digests_are_not_the_same_value():
    e = _env()
    assert e.claim_sha256() != e.content_sha256()

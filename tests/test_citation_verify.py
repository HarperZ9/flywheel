"""Offset-bound citations: a quote is a byte range of a frozen source,
and the verifier re-slices the source and compares hashes. Verified means
the bytes are there; drift means the slice no longer hashes to the quote;
unverifiable means the source cannot be resolved at all. A citation the
verifier cannot check is never counted as verified."""

import hashlib

from harness.envelope import ProofEnvelope, verify_citations

SRC = b"The Hubble constant is 73.17 +/- 0.86 km/s/Mpc per SH0ES 2024."
SHA = hashlib.sha256(SRC).hexdigest()


def _cite(start, end, quote_of=None):
    quote = SRC[start:end] if quote_of is None else quote_of
    return {"source_sha256": SHA, "start_byte": start, "end_byte": end,
            "quote_sha256": hashlib.sha256(quote).hexdigest()}


def _resolver(store):
    return lambda sha: store.get(sha)


def test_verified_citation_round_trips():
    out = verify_citations([_cite(23, 37)], _resolver({SHA: SRC}))
    assert out["verdicts"][0]["verdict"] == "verified"
    assert out["all_verified"] is True


def test_drift_when_the_slice_no_longer_matches():
    out = verify_citations([_cite(23, 37, quote_of=b"67.4 +/- 0.5")],
                           _resolver({SHA: SRC}))
    assert out["verdicts"][0]["verdict"] == "drift"
    assert out["all_verified"] is False


def test_unverifiable_when_the_source_cannot_be_resolved():
    out = verify_citations([_cite(23, 37)], _resolver({}))
    assert out["verdicts"][0]["verdict"] == "unverifiable"
    assert out["all_verified"] is False


def test_out_of_range_offsets_are_drift_not_crash():
    out = verify_citations([_cite(0, 10 ** 6)], _resolver({SHA: SRC}))
    assert out["verdicts"][0]["verdict"] == "drift"


def test_envelope_carries_citations_in_its_content_hash():
    base = dict(task_id="t", candidate="c", oracle="pytest",
                oracle_cmd="x", oracle_output_hash="h", verdict="PASS",
                model_ref="m", seed=1, prompt_hash="p", budget_spent={})
    bare = ProofEnvelope(**base)
    cited = ProofEnvelope(**base, citations=[_cite(23, 37)])
    assert cited.citations
    assert bare.content_sha256() != cited.content_sha256(), \
        "citations are part of the claim and must move the content hash"

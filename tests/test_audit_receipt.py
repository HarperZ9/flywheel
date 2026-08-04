"""Tests for the audit receipt: seal round-trip, tamper refusal, and the chain.

The audit receipt (Layer 2) seals a developer-facing judgment and CHAINS it onto
the work receipt it reviewed. These tests prove the seal refuses a flipped byte,
the chain link verifies against the exact work receipt and a wrong prev is
CHAIN_BROKEN, a foreign schema is UNVERIFIABLE, and the sealed body keeps the
no-floats / no-absolute-path discipline every receipt here holds.
"""
from __future__ import annotations

import json

from harness.audit_receipt import (
    MATCH,
    TAMPERED,
    UNVERIFIABLE,
    build_audit_receipt,
    verify_audit_receipt,
)
from harness.tool_call_receipt import build_receipt

_GOOD_DIGEST = "a" * 64


def _work_receipt():
    """A real sealed work receipt to chain onto."""
    return build_receipt(
        tool="write", capability="builtin-write", admission="ALLOWED",
        args={"path": "x"}, output="done", ok=True, rc=0, run_id="w1", seq=1)


def _audit_for(work, **over):
    kw = dict(
        run_id="audit-1",
        work_receipt_sha256=work["seal"]["hex"],
        subject_digest=_GOOD_DIGEST,
        reviewer="flywheel-audit/starter",
        reviews=[{"detector_id": "receipt_integrity", "dimension": "correctness",
                  "severity": "INFO", "summary": "the work receipt seal re-derives"}],
        summary="verdict PASS over 1 review(s).",
        verdict="PASS",
        confidence="moderate",
        does_not_prove="a cheap post-work review, not a proof.",
        started_utc="2026-08-04T00:00:00+00:00",
        finished_utc="2026-08-04T00:00:01+00:00",
    )
    kw.update(over)
    return build_audit_receipt(**kw)


def _scalars(obj):
    """Every scalar value in a nested dict/list, for the no-floats / no-path check."""
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _scalars(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _scalars(v)
    else:
        yield obj


def test_seal_round_trips_match():
    work = _work_receipt()
    receipt = _audit_for(work)
    v = verify_audit_receipt(receipt)
    assert v["verdict"] == MATCH, v


def test_tamper_a_review_verdict_is_refused():
    work = _work_receipt()
    receipt = _audit_for(work)
    # Flip a sealed field (a review's severity) on a COPY. The seal must refuse.
    copy = json.loads(json.dumps(receipt))
    copy["reviews"][0]["severity"] = "CRITICAL"
    v = verify_audit_receipt(copy)
    assert v["verdict"] == TAMPERED
    assert v["failure_class"] == "SEAL_MISMATCH"


def test_flip_one_seal_byte_is_refused():
    work = _work_receipt()
    receipt = _audit_for(work)
    copy = json.loads(json.dumps(receipt))
    hx = list(copy["seal"]["hex"])
    hx[0] = "0" if hx[0] != "0" else "1"
    copy["seal"]["hex"] = "".join(hx)
    v = verify_audit_receipt(copy)
    assert v["verdict"] == TAMPERED
    assert v["failure_class"] == "SEAL_MISMATCH"


def test_chain_link_verifies_against_the_work_receipt():
    work = _work_receipt()
    receipt = _audit_for(work)
    assert receipt["prev_receipt_sha256"] == work["seal"]["hex"]
    v = verify_audit_receipt(receipt, work_receipt=work)
    assert v["verdict"] == MATCH
    assert v["prev_receipt_sha256"] == work["seal"]["hex"]


def test_wrong_prev_is_chain_broken():
    work = _work_receipt()
    # An audit that chained to a DIFFERENT work receipt's hash.
    other = build_receipt(tool="read", capability="builtin-read", admission="ALLOWED",
                          args={}, output="x", ok=True, rc=0, run_id="w2", seq=1)
    receipt = _audit_for(work, work_receipt_sha256=other["seal"]["hex"])
    v = verify_audit_receipt(receipt, work_receipt=work)
    assert v["verdict"] == TAMPERED
    assert v["failure_class"] == "CHAIN_BROKEN"


def test_wrong_schema_is_unverifiable():
    work = _work_receipt()
    receipt = _audit_for(work)
    copy = json.loads(json.dumps(receipt))
    copy["schema"] = "flywheel.something-else/v1"
    v = verify_audit_receipt(copy)
    assert v["verdict"] == UNVERIFIABLE
    assert v["failure_class"] == "MALFORMED"


def test_empty_does_not_prove_is_a_field_contract_violation():
    # A built receipt with an empty honest null must be refused (not MATCH).
    work = _work_receipt()
    receipt = _audit_for(work, does_not_prove="")
    v = verify_audit_receipt(receipt)
    assert v["verdict"] == UNVERIFIABLE
    assert v["failure_class"] == "FIELD_CONTRACT_VIOLATION"


def test_body_has_no_float_and_no_absolute_path():
    work = _work_receipt()
    receipt = _audit_for(work)
    for s in _scalars(receipt):
        assert not isinstance(s, float), f"float in the sealed body: {s!r}"
        if isinstance(s, str):
            # no drive-letter path, no backslash path segment anywhere
            assert "\\" not in s, f"backslash (path) in the body: {s!r}"
            assert not (len(s) > 1 and s[1] == ":" and s[0].isalpha()), \
                f"drive-letter path in the body: {s!r}"

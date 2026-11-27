"""Tests for harness.remedy (I11 Check-Contest-Obtain-Remedy receipt protocol)."""

from __future__ import annotations

import copy
import pytest

from harness.contest import Contest, ContestReason
from harness.fsp.crypto import Ed25519Signer
from harness.remedy import (
    ContestedOutput,
    RemedyAction,
    RemedyError,
    RemedyVerdict,
    adjudicate_contest,
    hash_bytes,
    verify_remedy_chain,
    verify_remedy_receipt,
)


def _signed_contest(signer: Ed25519Signer, claim_sha: str, statement: str = "Output diverged from oracle") -> Contest:
    draft = Contest(
        disputed_claim_sha256=claim_sha,
        reason=ContestReason.CANNOT_REPRODUCE,
        statement=statement,
        contester_key_id="contester-01",
        contester_public_key=signer.public_hex(),
    )
    sig = signer.sign(draft.signing_payload().encode("utf-8"))
    return draft.attach_signature(sig)


def test_remedy_protocol_upheld_overturned_and_remedy_issued_chain() -> None:
    signer = Ed25519Signer.from_seed(b"\x11" * 32)
    out1, trace1 = b'{"answer": 42}', b'{"steps": ["eval(6*7)=42"]}'
    co1 = ContestedOutput("out-1", hash_bytes(out1), hash_bytes(trace1))
    c1 = _signed_contest(signer, co1.claim_sha256, "Disputing arithmetic result")

    r1 = adjudicate_contest(
        c1, co1, output_bytes=out1, audit_trace_bytes=trace1,
        oracle_fn=lambda o, _t: (RemedyVerdict.UPHELD, o, "Deterministic rerun matched 42."),
        oracle_id="arith-oracle-v1",
    )
    assert verify_remedy_receipt(r1, output_bytes=out1, audit_trace_bytes=trace1) == (True, "MATCH")
    assert verify_remedy_receipt(r1.to_dict()) == (True, "MATCH")

    out2, trace2 = b'{"answer": 41}', b'{"steps": ["off_by_one"]}'
    co2 = ContestedOutput("out-2", hash_bytes(out2), hash_bytes(trace2))
    c2 = _signed_contest(signer, co2.claim_sha256, "Off-by-one error in response")
    r2 = adjudicate_contest(
        c2, co2, output_bytes=out2, audit_trace_bytes=trace2,
        oracle_fn=lambda _o, _t: (RemedyVerdict.REMEDY_ISSUED, b'{"answer": 42}', "Corrected output emitted."),
        oracle_id="arith-oracle-v1",
        prev_receipt_sha256=r1.receipt_sha256,
    )
    assert r2.verdict == RemedyVerdict.REMEDY_ISSUED
    assert r2.remedy.action_kind == "re_execution"
    assert verify_remedy_receipt(r2, output_bytes=out2, audit_trace_bytes=trace2) == (True, "MATCH")

    out3, trace3 = b'{"claim": "unverified"}', b'{"steps": ["missing_citation"]}'
    co3 = ContestedOutput("out-3", hash_bytes(out3), hash_bytes(trace3))
    c3 = _signed_contest(signer, co3.claim_sha256, "Citation absent from source log")
    r3 = adjudicate_contest(
        c3, co3, output_bytes=out3, audit_trace_bytes=trace3,
        oracle_fn=lambda _o, _t: (RemedyVerdict.OVERTURNED, b"overturned", "Source check failed."),
        oracle_id="citation-oracle-v1",
        prev_receipt_sha256=r2.receipt_sha256,
    )
    ok_chain, verdict_chain, root = verify_remedy_chain([r1, r2, r3])
    assert ok_chain and verdict_chain == "MATCH" and root.startswith("sha256:")


def test_planted_forged_and_unsigned_appeals_fail_closed() -> None:
    signer = Ed25519Signer.from_seed(b"\x22" * 32)
    attacker = Ed25519Signer.from_seed(b"\x33" * 32)
    out, trace = b"contested-output", b"audit-trace-v1"
    co = ContestedOutput("out-forge", hash_bytes(out), hash_bytes(trace))

    unsigned = Contest(co.claim_sha256, ContestReason.CHECKER_IS_WRONG, "Unsigned dispute", "k1", signer.public_hex())
    with pytest.raises(RemedyError, match="FORGED_OR_UNSIGNED_CONTEST:unsigned"):
        adjudicate_contest(
            unsigned, co, output_bytes=out, audit_trace_bytes=trace,
            oracle_fn=lambda o, _t: (RemedyVerdict.UPHELD, o, "n/a"), oracle_id="o1",
        )

    # Attacker signs payload using their own key while naming victim's public key
    forged_sig = attacker.sign(unsigned.signing_payload().encode("utf-8"))
    forged = unsigned.attach_signature(forged_sig)
    with pytest.raises(RemedyError, match="FORGED_OR_UNSIGNED_CONTEST:bad_signature"):
        adjudicate_contest(
            forged, co, output_bytes=out, audit_trace_bytes=trace,
            oracle_fn=lambda o, _t: (RemedyVerdict.UPHELD, o, "n/a"), oracle_id="o1",
        )


def test_planted_broken_trace_hash_output_mismatch_and_claim_mismatch_fail_closed() -> None:
    signer = Ed25519Signer.from_seed(b"\x44" * 32)
    out, trace = b"model-output-bytes", b"original-audit-trace"
    co = ContestedOutput("out-trace", hash_bytes(out), hash_bytes(trace))
    contest = _signed_contest(signer, co.claim_sha256)

    with pytest.raises(RemedyError, match="AUDIT_TRACE_HASH_MISMATCH"):
        adjudicate_contest(
            contest, co, output_bytes=out, audit_trace_bytes=b"tampered-audit-trace",
            oracle_fn=lambda o, _t: (RemedyVerdict.UPHELD, o, "ok"), oracle_id="o1",
        )

    with pytest.raises(RemedyError, match="OUTPUT_HASH_MISMATCH"):
        adjudicate_contest(
            contest, co, output_bytes=b"tampered-output-bytes", audit_trace_bytes=trace,
            oracle_fn=lambda o, _t: (RemedyVerdict.UPHELD, o, "ok"), oracle_id="o1",
        )

    wrong_claim_contest = _signed_contest(signer, hash_bytes(b"different-claim"))
    with pytest.raises(RemedyError, match="CLAIM_BINDING_MISMATCH"):
        adjudicate_contest(
            wrong_claim_contest, co, output_bytes=out, audit_trace_bytes=trace,
            oracle_fn=lambda o, _t: (RemedyVerdict.UPHELD, o, "ok"), oracle_id="o1",
        )


def test_planted_post_seal_receipt_tamper_and_broken_chain_fail_closed() -> None:
    signer = Ed25519Signer.from_seed(b"\x55" * 32)
    out, trace = b"payload-a", b"trace-a"
    co = ContestedOutput("out-a", hash_bytes(out), hash_bytes(trace))
    c = _signed_contest(signer, co.claim_sha256)
    rec = adjudicate_contest(
        c, co, output_bytes=out, audit_trace_bytes=trace,
        oracle_fn=lambda o, _t: (RemedyVerdict.REMEDY_ISSUED, b"fixed-a", "Remedy issued."),
        oracle_id="oracle-a",
    )

    tampered = copy.deepcopy(rec.to_dict())
    tampered["verdict"] = "UPHELD"
    tampered["remedy"] = {"action_kind": "none", "summary": "", "artifact_sha256": ""}
    ok_t, why_t = verify_remedy_receipt(tampered)
    assert not ok_t and why_t == "RECEIPT_DIGEST_TAMPERED"

    # Broken chain link (second receipt points to genesis instead of rec.receipt_sha256)
    out2, trace2 = b"payload-b", b"trace-b"
    co2 = ContestedOutput("out-b", hash_bytes(out2), hash_bytes(trace2))
    c2 = _signed_contest(signer, co2.claim_sha256, "Second dispute")
    rec2 = adjudicate_contest(
        c2, co2, output_bytes=out2, audit_trace_bytes=trace2,
        oracle_fn=lambda o, _t: (RemedyVerdict.UPHELD, o, "Confirmed."),
        oracle_id="oracle-a",
        prev_receipt_sha256="genesis",
    )
    ok_c, why_c, _ = verify_remedy_chain([rec, rec2])
    assert not ok_c and why_c == "CHAIN_LINK_BROKEN_AT_1"

    # Verdict / remedy mismatch fails closed
    with pytest.raises(RemedyError, match="UPHELD verdict cannot attach"):
        adjudicate_contest(
            c, co, output_bytes=out, audit_trace_bytes=trace,
            oracle_fn=lambda o, _t: (RemedyVerdict.UPHELD, o, "Confirmed."),
            oracle_id="oracle-a",
            remedy_builder=lambda _v, _e: RemedyAction("rollback", "improper remedy"),
        )

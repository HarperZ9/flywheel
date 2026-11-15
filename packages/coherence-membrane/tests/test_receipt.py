"""Tests for signed observation receipts -- the external anchor across the seam."""

from __future__ import annotations

from coherence_membrane.observation import Observation, Provenance, Status
from coherence_membrane.receipt import (
    DRIFT,
    UNVERIFIABLE,
    VALID,
    WitnessReceipt,
    emit_receipt,
    verify_receipt,
)


def _obs(subject="frame.png", identity="a" * 64, **extra):
    data = {"identity_sha256": identity, "perceptual_hash": "00ff00ff00ff00ff"}
    data.update(extra)
    return Observation(
        organ="visual-artifact", subject=subject, summary="observed", status=Status.PASS,
        provenance=Provenance.witness_bytes(subject, b"x", "high"), data=data,
    )


def test_emit_receipt_carries_witnessed_facts():
    rec = emit_receipt(_obs(width=8, height=8, format="png"))
    assert rec.organ == "visual-artifact" and rec.subject == "frame.png"
    assert rec.digest.startswith("sha256:") and len(rec.digest) == len("sha256:") + 64
    assert rec.facts["identity_sha256"] == "a" * 64
    assert rec.facts["perceptual_hash"] == "00ff00ff00ff00ff"
    assert rec.facts["width"] == 8 and rec.facts["format"] == "png"


def test_anchor_is_deterministic_and_roundtrips():
    rec = emit_receipt(_obs())
    anchor = rec.anchor()
    assert len(anchor) == 64
    assert rec.anchor() == anchor  # stable
    again = WitnessReceipt.from_dict(rec.to_dict())
    assert again.anchor() == anchor  # survives serialisation


def test_verify_without_anchor_is_unverifiable():
    v = verify_receipt(emit_receipt(_obs()))
    assert v.verdict == UNVERIFIABLE
    assert "not tamper-evidence" in v.reason


def test_verify_matching_anchor_is_valid():
    rec = emit_receipt(_obs())
    assert verify_receipt(rec, pinned_anchor=rec.anchor()).verdict == VALID


def test_verify_wrong_anchor_is_drift():
    rec = emit_receipt(_obs())
    assert verify_receipt(rec, pinned_anchor="0" * 64).verdict == DRIFT


def test_changed_facts_change_the_anchor():
    pinned = emit_receipt(_obs(identity="a" * 64)).anchor()
    drifted = emit_receipt(_obs(identity="b" * 64))  # different witnessed identity
    assert verify_receipt(drifted, pinned_anchor=pinned).verdict == DRIFT


def test_embedded_anchor_is_not_trusted():
    # to_dict() carries a convenience anchor, but verify recomputes from content:
    # tampering the embedded anchor cannot make a changed receipt verify VALID.
    rec = emit_receipt(_obs(identity="a" * 64))
    pinned = rec.anchor()
    d = emit_receipt(_obs(identity="c" * 64)).to_dict()
    d["anchor"] = pinned  # forge the embedded anchor to the pinned value
    forged = WitnessReceipt.from_dict(d)
    assert verify_receipt(forged, pinned_anchor=pinned).verdict == DRIFT


def test_signature_verifier_accepts():
    rec = emit_receipt(_obs())
    assert verify_receipt(rec, signature_verifier=lambda r: True).verdict == VALID


def test_signature_verifier_rejects():
    rec = emit_receipt(_obs())
    assert verify_receipt(rec, signature_verifier=lambda r: False).verdict == DRIFT


def test_signature_verifier_that_raises_fails_closed():
    def boom(_r):
        raise RuntimeError("verifier exploded")

    v = verify_receipt(emit_receipt(_obs()), signature_verifier=boom)
    assert v.verdict == DRIFT  # never VALID on a raising verifier


def test_anchor_is_bound_to_an_emit_time_snapshot():
    # the receipt must snapshot facts; mutating the source observation's nested
    # list afterward must NOT change the receipt's anchor.
    o = _obs(region_hashes=["00" * 8, "11" * 8])
    rec = emit_receipt(o)
    anchor = rec.anchor()
    o.data["region_hashes"].append("22" * 8)  # mutate the source after emit
    assert rec.anchor() == anchor
    assert rec.facts["region_hashes"] == ["00" * 8, "11" * 8]


def test_signature_verifier_takes_precedence_over_anchor():
    # documented precedence: when both are supplied, the verifier is the authority
    # and pinned_anchor is not checked.
    rec = emit_receipt(_obs())
    v = verify_receipt(rec, signature_verifier=lambda r: True, pinned_anchor="0" * 64)
    assert v.verdict == VALID


def test_modality_agnostic_facts():
    audio = _obs(subject="clip.wav", perceptual_hash=None,
                 perceptual_audio_hash="0f0f0f0f0f0f0f0f")
    rec = emit_receipt(audio)
    assert rec.facts["perceptual_audio_hash"] == "0f0f0f0f0f0f0f0f"
    # a None perceptual_hash is still present in data -> excluded only if absent
    structured = _obs(subject="c.json", canonical_sha256="d" * 64)
    rec2 = emit_receipt(structured)
    assert rec2.facts["canonical_sha256"] == "d" * 64

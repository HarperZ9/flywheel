"""Tests for baseline memory -- drift against an authorized baseline."""

from __future__ import annotations

import pytest

from coherence_membrane.baseline import Baseline, BaselineEntry
from coherence_membrane.observation import Observation, Provenance, Status
from coherence_membrane.phash import DRIFT, MATCH, UNVERIFIABLE


def _obs(subject, identity, fingerprint=None, organ="visual-artifact", fp_key="perceptual_hash"):
    data = {"identity_sha256": identity}
    if fingerprint is not None:
        data[fp_key] = fingerprint
    return Observation(
        organ=organ,
        subject=subject,
        summary="observed",
        status=Status.PASS,
        provenance=Provenance.witness_bytes(subject, b"x", "high"),
        data=data,
    )


def test_no_baseline_is_unverifiable():
    b = Baseline()
    v = b.check(_obs("frame.png", "a" * 64))
    assert v.verdict == UNVERIFIABLE


def test_pinned_then_match():
    b = Baseline()
    b.pin(_obs("frame.png", "a" * 64, "00ff00ff00ff00ff"))
    v = b.check(_obs("frame.png", "a" * 64, "00ff00ff00ff00ff"))
    assert v.verdict == MATCH
    assert v.distance == 0


def test_drift_with_distance():
    b = Baseline()
    b.pin(_obs("frame.png", "a" * 64, "0000000000000000"))
    v = b.check(_obs("frame.png", "b" * 64, "000000000000000f"))
    assert v.verdict == DRIFT
    assert v.distance == 4


def test_drift_without_fingerprint_is_unquantified():
    b = Baseline()
    b.pin(_obs("frame.png", "a" * 64, None))
    v = b.check(_obs("frame.png", "b" * 64, None))
    assert v.verdict == DRIFT
    assert v.distance is None


def test_baseline_is_modality_agnostic_audio():
    b = Baseline()
    b.pin(_obs("clip.wav", "a" * 64, "00ff00ff00ff00ff",
               organ="audio-artifact", fp_key="perceptual_audio_hash"))
    same = b.check(_obs("clip.wav", "a" * 64, "00ff00ff00ff00ff",
                        organ="audio-artifact", fp_key="perceptual_audio_hash"))
    assert same.verdict == MATCH
    changed = b.check(_obs("clip.wav", "c" * 64, "00ff00ff00ff000f",
                           organ="audio-artifact", fp_key="perceptual_audio_hash"))
    assert changed.verdict == DRIFT and changed.distance is not None


def test_pin_requires_identity():
    b = Baseline()
    obs = Observation("o", "s", "x", Status.PASS,
                      Provenance.witness_bytes("s", b"x", "high"), data={})
    with pytest.raises(ValueError):
        b.pin(obs)


def test_save_and_load_roundtrip(tmp_path):
    b = Baseline()
    b.pin(_obs("frame.png", "a" * 64, "00ff00ff00ff00ff"))
    path = tmp_path / "baseline.json"
    b.save(path)
    loaded = Baseline.load(path)
    v = loaded.check(_obs("frame.png", "a" * 64, "00ff00ff00ff00ff"))
    assert v.verdict == MATCH


# --- semantic (canonical) drift, for structured data ----------------------


def _doc(subject, identity, canonical=None):
    data = {"identity_sha256": identity}
    if canonical is not None:
        data["canonical_sha256"] = canonical
    return Observation(
        organ="structured-data", subject=subject, summary="observed",
        status=Status.PASS, provenance=Provenance.witness_bytes(subject, b"x", "high"),
        data=data,
    )


def test_canonical_match_when_bytes_differ_but_canonical_equal():
    b = Baseline()
    b.pin(_doc("config.json", "a" * 64, canonical="c" * 64))
    # different raw bytes, same canonical form (e.g. reformatted JSON)
    v = b.check(_doc("config.json", "b" * 64, canonical="c" * 64))
    assert v.verdict == MATCH
    assert "canonical" in v.reason


def test_canonical_drift_when_canonical_differs():
    b = Baseline()
    b.pin(_doc("config.json", "a" * 64, canonical="c" * 64))
    v = b.check(_doc("config.json", "b" * 64, canonical="d" * 64))
    assert v.verdict == DRIFT
    assert v.distance is None
    assert "canonical" in v.reason


def test_exact_identity_still_wins_over_canonical():
    b = Baseline()
    b.pin(_doc("config.json", "a" * 64, canonical="c" * 64))
    v = b.check(_doc("config.json", "a" * 64, canonical="c" * 64))
    assert v.verdict == MATCH
    assert "identity equal" in v.reason


def test_canonical_roundtrips_through_save_load(tmp_path):
    b = Baseline()
    b.pin(_doc("config.json", "a" * 64, canonical="c" * 64))
    path = tmp_path / "baseline.json"
    b.save(path)
    loaded = Baseline.load(path)
    # reformatted (byte-different, canonical-equal) still matches after reload
    v = loaded.check(_doc("config.json", "z" * 64, canonical="c" * 64))
    assert v.verdict == MATCH


def test_cross_organ_subject_collision_is_unverifiable():
    # bytes-fed observations share the subject "<bytes>"; a baseline pinned by one
    # organ must not adjudicate another organ's observation on that colliding key.
    b = Baseline()
    b.pin(_obs("<bytes>", "a" * 64, organ="caption-text"))
    v = b.check(_obs("<bytes>", "a" * 64, organ="visual-artifact"))
    assert v.verdict == UNVERIFIABLE


def test_from_dict_tolerates_pre_canonical_baseline():
    # a baseline written before increment 6 has no canonical_sha256 key at all;
    # loading it must not raise and must default the field to None.
    entry = BaselineEntry.from_dict({
        "organ": "visual-artifact", "subject": "frame.png",
        "identity_sha256": "a" * 64, "fingerprint": "00ff00ff00ff00ff",
    })
    assert entry.canonical_sha256 is None

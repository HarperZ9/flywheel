"""Tests for the observation contract."""

from __future__ import annotations

import hashlib

from coherence_membrane.observation import (
    Observation,
    Provenance,
    Status,
    sha256_hex,
)


def test_sha256_full_width():
    h = sha256_hex(b"hello")
    assert len(h) == 64
    assert h == hashlib.sha256(b"hello").hexdigest()


def test_witness_bytes_digest_and_timestamp():
    p = Provenance.witness_bytes("artifact", b"data", "high")
    assert p.digest == "sha256:" + hashlib.sha256(b"data").hexdigest()
    assert p.timestamp  # non-empty ISO timestamp
    assert p.confidence == "high"


def test_observation_roundtrip():
    obs = Observation(
        organ="visual-artifact",
        subject="frame.png",
        summary="artifact observed",
        status=Status.PASS,
        provenance=Provenance.witness_bytes("frame.png", b"x", "high"),
        data={"identity_sha256": sha256_hex(b"x"), "width": 4},
    )
    restored = Observation.from_dict(obs.to_dict())
    assert restored == obs


def test_status_has_no_authority_value():
    values = {s.value for s in Status}
    forbidden = {"trusted", "approved", "authorized", "allowed", "certified"}
    assert values.isdisjoint(forbidden)


def test_provenance_command_optional_in_dict():
    p = Provenance.witness_bytes("s", b"y", "low")
    assert "command" not in p.to_dict()
    p2 = Provenance.witness_bytes("s", b"y", "low", command="git status")
    assert p2.to_dict()["command"] == "git status"

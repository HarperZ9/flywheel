"""Tests for the inert VisualArtifactOrgan."""

from __future__ import annotations

import hashlib

from coherence_membrane.observation import Status
from coherence_membrane.organs.visual import VisualArtifactOrgan


def test_observe_png_bytes(make_png):
    png = make_png(4, 3, bytes((i * 5) % 256 for i in range(4 * 3 * 3)), color_type=2)
    obs = VisualArtifactOrgan().observe(png)[0]
    assert obs.organ == "visual-artifact"
    assert obs.status == Status.PASS
    assert obs.data["identity_sha256"] == hashlib.sha256(png).hexdigest()
    assert obs.data["width"] == 4 and obs.data["height"] == 3
    assert obs.data["format"] == "png"
    assert obs.data["decoded"] is True
    assert len(obs.data["perceptual_hash"]) == 16  # 64-bit hex


def test_observe_is_reproducible(make_png):
    png = make_png(8, 8, bytes((i * 3) % 256 for i in range(8 * 8 * 3)))
    organ = VisualArtifactOrgan()
    a = organ.observe(png)[0]
    b = organ.observe(png)[0]
    assert a.data["identity_sha256"] == b.data["identity_sha256"]
    assert a.data["perceptual_hash"] == b.data["perceptual_hash"]


def test_observe_non_png_bytes_is_identity_only():
    obs = VisualArtifactOrgan().observe(b"this is not a png")[0]
    assert obs.status == Status.UNVERIFIED
    assert obs.data["format"] == "unknown"
    assert obs.data["perceptual_hash"] is None
    # identity is still witnessed, even for an unperceivable artifact
    assert obs.data["identity_sha256"] == hashlib.sha256(b"this is not a png").hexdigest()


def test_observe_missing_path_is_unverified(tmp_path):
    missing = tmp_path / "nope.png"
    obs = VisualArtifactOrgan().observe(missing)[0]
    assert obs.status == Status.UNVERIFIED
    assert obs.data["decoded"] is False


def test_observe_reads_from_path(make_png, tmp_path):
    png = make_png(2, 2, bytes(12))
    p = tmp_path / "frame.png"
    p.write_bytes(png)
    obs = VisualArtifactOrgan().observe(p)[0]
    assert obs.data["identity_sha256"] == hashlib.sha256(png).hexdigest()
    assert obs.status == Status.PASS


def test_structurally_valid_but_undecodable_png_is_unverified(make_png):
    # an interlaced PNG: the IHDR reads fine but decode_png rejects it. Pixels
    # were not perceived, so status must be UNVERIFIED (not a full PASS).
    png = bytearray(make_png(4, 4, bytes(4 * 4 * 3)))
    png[28] = 1  # flip the IHDR interlace byte (CRC unchecked by the decoder)
    obs = VisualArtifactOrgan().observe(bytes(png))[0]
    assert obs.data["format"] == "png"      # header still witnessed
    assert obs.data["decoded"] is False
    assert obs.data["perceptual_hash"] is None
    assert obs.status == Status.UNVERIFIED  # not a silent PASS


def test_selftest_passes():
    result = VisualArtifactOrgan().selftest()
    assert result.passed, result.to_dict()
    assert len(result.checks) >= 4


def test_organ_does_not_mutate_input_file(make_png, tmp_path):
    png = make_png(4, 4, bytes(4 * 4 * 3))
    p = tmp_path / "frame.png"
    p.write_bytes(png)
    before = p.read_bytes()
    VisualArtifactOrgan().observe(p)
    assert p.read_bytes() == before  # inert: observation never writes

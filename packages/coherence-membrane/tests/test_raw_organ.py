"""Tests for the RawFrameOrgan -- sight on the encode-free fast path."""

from __future__ import annotations

import hashlib

from coherence_membrane.capture import Frame, FrameDescriptor
from coherence_membrane.observation import Status
from coherence_membrane.organs.raw import RawFrameOrgan
from coherence_membrane.organs.visual import VisualArtifactOrgan
from coherence_membrane.pngencode import bgra_to_rgb, encode_png


def test_observe_raw_bgra_frame(raw_bgra_frame):
    frame, payload, w, h = raw_bgra_frame(9, 8)
    obs = RawFrameOrgan().observe(frame)[0]
    assert obs.organ == "raw-frame"
    assert obs.status == Status.PASS
    assert obs.data["identity_sha256"] == hashlib.sha256(payload).hexdigest()
    assert obs.data["width"] == 9 and obs.data["height"] == 8
    assert obs.data["format"] == "bgra"
    assert obs.data["decoded"] is True
    assert len(obs.data["perceptual_hash"]) == 16  # 64-bit hex


def test_raw_hash_equals_png_path(raw_bgra_frame):
    """The headline guarantee: the raw fast path yields the SAME perceptual hash
    as encoding to PNG and perceiving that -- only the cost differs, not the answer."""
    frame, payload, w, h = raw_bgra_frame(16, 16)
    raw_ph = RawFrameOrgan().observe(frame)[0].data["perceptual_hash"]

    png = encode_png(w, h, bgra_to_rgb(payload, w, h), channels=3)
    png_ph = VisualArtifactOrgan().observe(png)[0].data["perceptual_hash"]

    assert raw_ph == png_ph
    assert raw_ph != "0000000000000000"  # non-trivial: not a vacuous match


def test_raw_identity_differs_from_png_identity(raw_bgra_frame):
    """Honesty: raw and PNG identities are of DIFFERENT byte streams, so they
    must NOT be equal even for the same pixels -- only the fingerprint matches."""
    frame, payload, w, h = raw_bgra_frame(8, 8)
    raw_id = RawFrameOrgan().observe(frame)[0].data["identity_sha256"]
    png = encode_png(w, h, bgra_to_rgb(payload, w, h), channels=3)
    png_id = VisualArtifactOrgan().observe(png)[0].data["identity_sha256"]
    assert raw_id != png_id


def test_changed_pixels_change_the_fingerprint(raw_bgra_frame):
    a, _, _, _ = raw_bgra_frame(16, 16, invert=False)
    b, _, _, _ = raw_bgra_frame(16, 16, invert=True)
    fa = RawFrameOrgan().observe(a)[0].data["perceptual_hash"]
    fb = RawFrameOrgan().observe(b)[0].data["perceptual_hash"]
    assert fa != fb


def test_observe_is_reproducible(raw_bgra_frame):
    frame, _, _, _ = raw_bgra_frame(12, 9)
    organ = RawFrameOrgan()
    a = organ.observe(frame)[0]
    b = organ.observe(frame)[0]
    assert a.data["identity_sha256"] == b.data["identity_sha256"]
    assert a.data["perceptual_hash"] == b.data["perceptual_hash"]


def test_non_frame_subject_returns_empty():
    organ = RawFrameOrgan()
    assert organ.observe(b"loose bytes with no geometry") == []
    assert organ.observe("some/path.bgra") == []


def test_missing_geometry_is_identity_only():
    payload = bytes([10, 20, 30, 255] * 16)
    frame = Frame(descriptor=FrameDescriptor(source_id="t", frame_index=0,
                                             pixel_format="bgra"), payload=payload)
    obs = RawFrameOrgan().observe(frame)[0]
    assert obs.status == Status.UNVERIFIED
    assert obs.data["perceptual_hash"] is None
    assert obs.data["identity_sha256"] == hashlib.sha256(payload).hexdigest()


def test_unknown_pixel_format_is_identity_only():
    payload = bytes([1, 2, 3, 4] * 16)
    frame = Frame(descriptor=FrameDescriptor(source_id="t", frame_index=0,
                                             width=4, height=4, pixel_format="yuv420"),
                  payload=payload)
    obs = RawFrameOrgan().observe(frame)[0]
    assert obs.status == Status.UNVERIFIED
    assert obs.data["perceptual_hash"] is None


def test_zero_dimension_fails_closed():
    # A known format ('bgra') with 0x0 geometry must NOT crash (it once reached
    # perceptual_hash_raw and raised an uncaught ValueError); it degrades.
    frame = Frame(descriptor=FrameDescriptor(source_id="t", frame_index=0,
                                             width=0, height=0, pixel_format="bgra"),
                  payload=bytes(64))
    obs = RawFrameOrgan().observe(frame)[0]
    assert obs.status == Status.UNVERIFIED
    assert obs.data["perceptual_hash"] is None


def test_negative_dimension_fails_closed():
    frame = Frame(descriptor=FrameDescriptor(source_id="t", frame_index=0,
                                             width=-16, height=16, pixel_format="bgra"),
                  payload=bytes(64))
    obs = RawFrameOrgan().observe(frame)[0]  # must not raise; negative dims degrade
    assert obs.status == Status.UNVERIFIED
    assert obs.data["perceptual_hash"] is None


def test_short_buffer_is_identity_only():
    # declares 16x16 BGRA (1024 bytes) but only provides 12
    payload = bytes(12)
    frame = Frame(descriptor=FrameDescriptor(source_id="t", frame_index=0,
                                             width=16, height=16, pixel_format="bgra"),
                  payload=payload)
    obs = RawFrameOrgan().observe(frame)[0]
    assert obs.status == Status.UNVERIFIED
    assert obs.data["perceptual_hash"] is None
    assert "decode_note" in obs.data


def test_selftest_passes():
    result = RawFrameOrgan().selftest()
    assert result.passed, result.to_dict()
    assert len(result.checks) >= 6

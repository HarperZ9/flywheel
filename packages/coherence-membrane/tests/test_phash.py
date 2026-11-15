"""Tests for perceptual hashing and the drift verdict lattice."""

from __future__ import annotations

from coherence_membrane.phash import (
    DRIFT,
    MATCH,
    UNVERIFIABLE,
    compare_drift,
    hamming,
    perceptual_hash,
    perceptual_hash_raw,
    raw_channels,
)
from coherence_membrane.pngencode import bgra_to_rgb, encode_png
from coherence_membrane.pngview import decode_png


def test_perceptual_hash_deterministic(gradient_rgb):
    img = decode_png(gradient_rgb())
    assert perceptual_hash(img) == perceptual_hash(img)


def test_identical_images_zero_distance(gradient_rgb):
    a = perceptual_hash(decode_png(gradient_rgb()))
    b = perceptual_hash(decode_png(gradient_rgb()))
    assert hamming(a, b) == 0


def test_different_images_nonzero_distance(gradient_rgb):
    normal = perceptual_hash(decode_png(gradient_rgb(invert=False)))
    inverted = perceptual_hash(decode_png(gradient_rgb(invert=True)))
    # An inverted horizontal gradient flips every adjacent comparison.
    assert hamming(normal, inverted) > 0


def test_hamming_basic():
    assert hamming(0b1010, 0b0011) == 2


# --- raw-pixel perceptual hash (the fast path) -----------------------------


def _bgra_gradient(w, h, invert=False):
    # Centre-peak tent in R (non-monotonic -> non-trivial dHash); horizontal ramp
    # in B with a DIFFERENT profile, so an R<->B swap changes the hash.
    cx = (w - 1) / 2 if w > 1 else 0.0
    px = bytearray()
    for _y in range(h):
        for x in range(w):
            r = int(255 * (1 - abs(x - cx) / cx)) if cx else 0
            if invert:
                r = 255 - r
            b = (x * 255) // (w - 1) if w > 1 else 0
            px += bytes([b, 64, r, 255])  # B, G, R, A
    return bytes(px)


def test_raw_channels_known_and_unknown():
    assert raw_channels("bgra") == 4
    assert raw_channels("rgb") == 3
    assert raw_channels("gray") == 1
    assert raw_channels("png") is None
    assert raw_channels(None) is None


def test_raw_hash_matches_decoded_png_hash():
    """perceptual_hash_raw(BGRA) == perceptual_hash(decode(encode(rgb))) -- the
    fast path is bit-identical to the encode/decode path for the same pixels."""
    w = h = 16
    bgra = _bgra_gradient(w, h)
    raw_h = perceptual_hash_raw(bgra, w, h, "bgra")
    png_h = perceptual_hash(decode_png(encode_png(w, h, bgra_to_rgb(bgra, w, h), channels=3)))
    assert raw_h == png_h
    assert raw_h != 0  # non-trivial: the equality is not vacuously 0 == 0


def test_raw_hash_deterministic():
    bgra = _bgra_gradient(12, 10)
    assert perceptual_hash_raw(bgra, 12, 10, "bgra") == perceptual_hash_raw(bgra, 12, 10, "bgra")


def test_raw_hash_is_byte_order_sensitive():
    """The same buffer read as bgra vs rgba (an R<->B swap) must hash
    DIFFERENTLY -- that is what makes the cross-path equality check able to catch
    a wrong _RAW_LAYOUTS entry, rather than passing vacuously on a symmetric
    pattern.  Requires R and B to have different horizontal profiles."""
    w = h = 16
    bgra = _bgra_gradient(w, h)
    assert perceptual_hash_raw(bgra, w, h, "bgra") != perceptual_hash_raw(bgra, w, h, "rgba")


def test_raw_hash_changes_on_visual_change():
    a = perceptual_hash_raw(_bgra_gradient(16, 16, invert=False), 16, 16, "bgra")
    b = perceptual_hash_raw(_bgra_gradient(16, 16, invert=True), 16, 16, "bgra")
    assert hamming(a, b) > 0


def test_raw_hash_rejects_short_buffer():
    try:
        perceptual_hash_raw(bytes(8), 16, 16, "bgra")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for a short raw buffer")


def test_raw_hash_rejects_unknown_format():
    try:
        perceptual_hash_raw(bytes(16 * 16 * 4), 16, 16, "yuv420")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for an unknown raw format")


# --- drift verdict lattice -------------------------------------------------


def test_drift_match_on_equal_sha():
    v = compare_drift("a" * 64, "a" * 64, 1, 2)
    assert v.verdict == MATCH
    assert v.distance == 0


def test_drift_on_differing_bytes_with_phashes():
    v = compare_drift("a" * 64, "b" * 64, 0b1111, 0b0000)
    assert v.verdict == DRIFT
    assert v.distance == 4


def test_unverifiable_when_phash_missing():
    v = compare_drift("a" * 64, "b" * 64, None, 5)
    assert v.verdict == UNVERIFIABLE
    assert v.distance is None


def test_unverifiable_when_identity_missing():
    v = compare_drift(None, "b" * 64, 1, 2)
    assert v.verdict == UNVERIFIABLE


def test_drift_never_silently_matches_on_diff():
    # Different bytes must never be MATCH.
    v = compare_drift("a" * 64, "c" * 64, 7, 7)
    assert v.verdict != MATCH

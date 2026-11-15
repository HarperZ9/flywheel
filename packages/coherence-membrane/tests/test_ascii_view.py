"""Tests for ASCII perception -- AsciiViewOrgan + ascii_view/compare_ascii_drift."""

from __future__ import annotations

import hashlib

from coherence_membrane.ascii_view import (
    ASCII_RAMP,
    ascii_text,
    ascii_view,
    compare_ascii_drift,
)
from coherence_membrane.observation import Status
from coherence_membrane.organs.ascii_view import AsciiViewOrgan
from coherence_membrane.pngencode import encode_png
from coherence_membrane.pngview import decode_png


def _uniform_png(value, w=8, h=8):
    return encode_png(w, h, bytes([value, value, value] * (w * h)), channels=3)


def test_observe_emits_ascii_grid():
    organ = AsciiViewOrgan(cols=20, rows=8)
    png = organ._make_png()
    obs = organ.observe(png)[0]
    assert obs.organ == "ascii-view" and obs.status == Status.PASS
    assert obs.data["identity_sha256"] == hashlib.sha256(png).hexdigest()
    assert obs.data["ascii_rows"] == 8 and obs.data["ascii_cols"] == 20
    assert len(obs.data["ascii_view"]) == 8
    assert all(len(r) == 20 for r in obs.data["ascii_view"])
    assert len(obs.data["perceptual_hash"]) == 16  # still slots into baseline
    assert len(obs.data["ascii_sha256"]) == 64


def test_ascii_ramp_maps_black_to_space_white_to_last():
    black = ascii_view(decode_png(_uniform_png(0)), cols=8, rows=4)
    white = ascii_view(decode_png(_uniform_png(255)), cols=8, rows=4)
    assert all(ch == ASCII_RAMP[0] for row in black for ch in row)      # darkest glyph
    assert all(ch == ASCII_RAMP[-1] for row in white for ch in row)     # brightest glyph


def test_ascii_view_deterministic():
    img = decode_png(_uniform_png(128))
    assert ascii_view(img, 12, 6) == ascii_view(img, 12, 6)


def test_ascii_view_rejects_non_positive_cols():
    img = decode_png(_uniform_png(128))
    for bad in (0, -3):
        try:
            ascii_view(img, bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected ValueError for cols={bad}")


def test_ascii_sha256_re_derives_from_grid():
    obs = AsciiViewOrgan(cols=16, rows=8).observe(AsciiViewOrgan()._make_png())[0]
    expected = hashlib.sha256(ascii_text(obs.data["ascii_view"]).encode("utf-8")).hexdigest()
    assert obs.data["ascii_sha256"] == expected


def test_visual_change_moves_the_glyphs():
    organ = AsciiViewOrgan(cols=16, rows=8)
    base = organ.observe(organ._make_png())[0].data["ascii_view"]
    changed = organ.observe(organ._make_png(invert=True))[0].data["ascii_view"]
    r = compare_ascii_drift(base, changed)
    assert r.verdict == "DRIFT" and r.changed_cells > 0
    assert r.total_cells == 16 * 8


def test_compare_ascii_drift_match():
    organ = AsciiViewOrgan(cols=10, rows=5)
    view = organ.observe(organ._make_png())[0].data["ascii_view"]
    r = compare_ascii_drift(view, view)
    assert r.verdict == "MATCH" and r.changed_cells == 0


def test_compare_ascii_drift_dimension_mismatch_is_unverifiable():
    assert compare_ascii_drift(["abc", "def"], ["abc"]).verdict == "UNVERIFIABLE"
    assert compare_ascii_drift(["abc"], ["abcd"]).verdict == "UNVERIFIABLE"  # width differs
    assert compare_ascii_drift(None, ["a"]).verdict == "UNVERIFIABLE"


def test_non_png_is_identity_only():
    obs = AsciiViewOrgan().observe(b"not a png")[0]
    assert obs.status == Status.UNVERIFIED
    assert obs.data["ascii_view"] is None
    assert obs.data["identity_sha256"] == hashlib.sha256(b"not a png").hexdigest()


def test_missing_path_is_unverified(tmp_path):
    obs = AsciiViewOrgan().observe(tmp_path / "nope.png")[0]
    assert obs.status == Status.UNVERIFIED and obs.data["decoded"] is False


def test_rejects_non_positive_cols_in_constructor():
    for bad in (0, -1):
        try:
            AsciiViewOrgan(cols=bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected ValueError for cols={bad}")


def test_selftest_passes():
    result = AsciiViewOrgan(cols=24).selftest()
    assert result.passed, result.to_dict()
    assert len(result.checks) >= 6


def test_organ_does_not_mutate_input_file(tmp_path):
    organ = AsciiViewOrgan()
    png = organ._make_png()
    p = tmp_path / "frame.png"
    p.write_bytes(png)
    before = p.read_bytes()
    organ.observe(p)
    assert p.read_bytes() == before  # inert

"""Tests for region/element perception -- RegionArtifactOrgan + compare_region_drift."""

from __future__ import annotations

import hashlib

from coherence_membrane.observation import Status
from coherence_membrane.organs.region import RegionArtifactOrgan
from coherence_membrane.pngview import decode_png
from coherence_membrane.region import compare_region_drift, tile_hashes


def _grid_png(organ, **kw):
    return organ._make_png(**kw)  # the organ's deterministic per-tile pattern


def test_observe_emits_region_grid():
    organ = RegionArtifactOrgan(rows=4, cols=4)
    png = _grid_png(organ)
    obs = organ.observe(png)[0]
    assert obs.organ == "region-visual"
    assert obs.status == Status.PASS
    assert obs.data["identity_sha256"] == hashlib.sha256(png).hexdigest()
    assert obs.data["grid_rows"] == 4 and obs.data["grid_cols"] == 4
    assert len(obs.data["region_hashes"]) == 16
    assert len(obs.data["perceptual_hash"]) == 16  # whole-image fingerprint too
    assert all(len(h) == 16 for h in obs.data["region_hashes"])


def test_localized_change_is_isolated_to_its_tile():
    organ = RegionArtifactOrgan(rows=4, cols=4)
    base = organ.observe(_grid_png(organ))[0]
    changed = organ.observe(_grid_png(organ, altered_tile=5))[0]
    report = compare_region_drift(base.data["region_hashes"], changed.data["region_hashes"], 4, 4)
    assert report.verdict == "DRIFT"
    assert report.changed_regions == [5]  # only the altered tile moved
    assert report.distances[5] > 0
    assert sum(1 for d in report.distances if d > 0) == 1


def test_compare_region_drift_match():
    organ = RegionArtifactOrgan(rows=2, cols=2)
    obs = organ.observe(_grid_png(organ))[0]
    report = compare_region_drift(obs.data["region_hashes"], obs.data["region_hashes"], 2, 2)
    assert report.verdict == "MATCH"
    assert report.changed_regions == []
    assert report.max_distance == 0


def test_compare_region_drift_grid_mismatch_is_unverifiable():
    report = compare_region_drift(["0000000000000000"] * 4, ["0000000000000000"] * 9, 2, 2)
    assert report.verdict == "UNVERIFIABLE"
    assert report.distances == []


def test_compare_region_drift_missing_grid_is_unverifiable():
    assert compare_region_drift(None, ["0" * 16] * 4, 2, 2).verdict == "UNVERIFIABLE"
    assert compare_region_drift([], ["0" * 16] * 4, 2, 2).verdict == "UNVERIFIABLE"


def test_compare_region_drift_threshold():
    base = ["0000000000000000", "0000000000000000"]
    cur = ["0000000000000000", "000000000000000f"]  # second tile distance 4
    assert compare_region_drift(base, cur, 1, 2, threshold=0).verdict == "DRIFT"
    assert compare_region_drift(base, cur, 1, 2, threshold=4).verdict == "MATCH"  # within threshold


def test_tile_hashes_count_and_validation():
    organ = RegionArtifactOrgan(rows=3, cols=5)
    img = decode_png(organ._make_png())
    assert len(tile_hashes(img, 3, 5)) == 15
    for bad in ((0, 4), (4, 0), (-1, 2)):
        try:
            tile_hashes(img, *bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected ValueError for rows,cols={bad}")


def test_custom_grid_dimensions():
    organ = RegionArtifactOrgan(rows=2, cols=8)
    obs = organ.observe(organ._make_png())[0]
    assert obs.data["grid_rows"] == 2 and obs.data["grid_cols"] == 8
    assert len(obs.data["region_hashes"]) == 16


def test_non_png_is_identity_only():
    obs = RegionArtifactOrgan().observe(b"not a png")[0]
    assert obs.status == Status.UNVERIFIED
    assert obs.data["region_hashes"] is None
    assert obs.data["identity_sha256"] == hashlib.sha256(b"not a png").hexdigest()


def test_missing_path_is_unverified(tmp_path):
    obs = RegionArtifactOrgan().observe(tmp_path / "nope.png")[0]
    assert obs.status == Status.UNVERIFIED
    assert obs.data["decoded"] is False


def test_observe_is_reproducible():
    organ = RegionArtifactOrgan()
    png = organ._make_png()
    a = organ.observe(png)[0]
    b = organ.observe(png)[0]
    assert a.data["region_hashes"] == b.data["region_hashes"]


def test_rejects_non_positive_grid():
    for bad in ((0, 4), (4, 0)):
        try:
            RegionArtifactOrgan(*bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected ValueError for {bad}")


def test_selftest_passes():
    result = RegionArtifactOrgan().selftest()
    assert result.passed, result.to_dict()
    assert len(result.checks) >= 5


def test_organ_does_not_mutate_input_file(tmp_path):
    organ = RegionArtifactOrgan()
    png = organ._make_png()
    p = tmp_path / "frame.png"
    p.write_bytes(png)
    before = p.read_bytes()
    organ.observe(p)
    assert p.read_bytes() == before  # inert

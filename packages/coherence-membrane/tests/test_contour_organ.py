from __future__ import annotations

from coherence_membrane.observation import Status, sha256_hex
from coherence_membrane.organs.contour import ContourViewOrgan
from coherence_membrane.pngencode import encode_png


def _half_png():
    # 16x16, left half dark, right half bright -> one vertical contour near x=7.5
    w = h = 16
    px = bytearray()
    for y in range(h):
        for x in range(w):
            v = 0 if x < w // 2 else 255
            px += bytes([v, v, v])
    return encode_png(w, h, bytes(px), channels=3)


def test_contour_organ_emits_witnessed_vector():
    payload = _half_png()
    obs = ContourViewOrgan().observe(payload)[0]
    assert obs.status == Status.PASS
    assert obs.data["identity_sha256"] == sha256_hex(payload)
    assert obs.data["path_count"] >= 1
    assert "<path" in obs.data["svg"]
    assert obs.data["coords"] != "empty"
    assert obs.data["algo"] == "marching-squares-v1"
    assert obs.provenance.digest.startswith("sha256:")
    assert len(obs.provenance.digest) == len("sha256:") + 64


def test_contour_organ_fail_closed_on_undecodable():
    bad = ContourViewOrgan().observe(b"not a png")[0]
    assert bad.status == Status.UNVERIFIED
    assert bad.data["identity_sha256"] == sha256_hex(b"not a png")


def test_contour_organ_selftest_passes():
    result = ContourViewOrgan().selftest()
    assert result.passed


def test_contour_organ_fail_closed_on_missing_file():
    # unreadable-subject branch: read fails -> UNVERIFIED, no identity claimed
    from pathlib import Path
    obs = ContourViewOrgan().observe(Path("does-not-exist.png"))[0]
    assert obs.status == Status.UNVERIFIED
    assert "identity_sha256" not in obs.data


def test_contour_organ_fail_closed_on_unsupported_type():
    obs = ContourViewOrgan().observe(123)[0]
    assert obs.status == Status.UNVERIFIED

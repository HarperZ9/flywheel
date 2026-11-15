from __future__ import annotations

from coherence_membrane.observation import Status, sha256_hex
from coherence_membrane.organs.color import ColorQuantizeOrgan
from coherence_membrane.pngencode import encode_png


def _two_color_png():
    # 2x1: black, white
    return encode_png(2, 1, bytes([0, 0, 0, 255, 255, 255]), channels=3)


def test_color_organ_emits_witnessed_palette():
    payload = _two_color_png()
    obs = ColorQuantizeOrgan(k=2).observe(payload)[0]
    assert obs.status == Status.PASS
    assert obs.data["identity_sha256"] == sha256_hex(payload)
    assert obs.data["num_colors"] == 2
    assert obs.data["algo"] == "oklab-medcut-v1"
    assert obs.data["delta_e_max"] < 1e-9              # 2 colors, 2 clusters -> exact
    assert set(obs.data["palette_hex"]) == {"#000000", "#ffffff"}
    assert obs.provenance.digest.startswith("sha256:")
    assert len(obs.provenance.digest) == len("sha256:") + 64


def test_color_organ_fail_closed_on_undecodable():
    bad = ColorQuantizeOrgan().observe(b"not a png")[0]
    assert bad.status == Status.UNVERIFIED
    assert bad.data["identity_sha256"] == sha256_hex(b"not a png")


def test_color_organ_selftest_passes():
    assert ColorQuantizeOrgan().selftest().passed

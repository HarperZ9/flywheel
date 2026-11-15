"""Tests for BrailleViewOrgan -- organ-level witness contract."""
from __future__ import annotations

from coherence_membrane.observation import Status, sha256_hex
from coherence_membrane.organs.braille import BrailleViewOrgan


def test_observe_emits_braille():
    organ = BrailleViewOrgan(cols=8, rows=4)
    png = organ._make_png()
    obs = organ.observe(png)[0]
    assert obs.organ == "braille-view"
    assert obs.status == Status.PASS
    assert obs.data["identity_sha256"] == sha256_hex(png)
    assert obs.data["braille"]
    assert obs.provenance.digest.startswith("sha256:")
    assert len(obs.provenance.digest) == len("sha256:") + 64


def test_observe_fail_closed_on_garbage():
    obs = BrailleViewOrgan().observe(b"not a png")[0]
    assert obs.status == Status.UNVERIFIED
    assert obs.data["identity_sha256"] == sha256_hex(b"not a png")


def test_observe_is_inert():
    organ = BrailleViewOrgan()
    png = organ._make_png()
    before = bytes(png)
    organ.observe(png)
    assert png == before


def test_selftest_passes():
    result = BrailleViewOrgan().selftest()
    assert result.passed
    assert len(result.checks) >= 4


def test_observe_missing_file_returns_unverified():
    # OUTER fail-closed: non-existent path -> Status.UNVERIFIED, no crash
    from pathlib import Path
    obs = BrailleViewOrgan().observe(Path("does-not-exist.png"))[0]
    assert obs.status == Status.UNVERIFIED


def test_observe_unsupported_type_returns_unverified():
    # OUTER fail-closed: unsupported subject type -> Status.UNVERIFIED, no crash
    obs = BrailleViewOrgan().observe(123)[0]
    assert obs.status == Status.UNVERIFIED

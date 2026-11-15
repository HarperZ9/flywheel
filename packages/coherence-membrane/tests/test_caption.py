"""Tests for the CaptionOrgan -- the membrane reads what was said."""

from __future__ import annotations

import hashlib

from coherence_membrane.baseline import Baseline
from coherence_membrane.observation import Status
from coherence_membrane.organs.caption import CaptionOrgan, canonical_caption


def test_observe_caption_bytes():
    text = b"A wolf howls at dusk."
    obs = CaptionOrgan().observe(text)[0]
    assert obs.organ == "caption-text" and obs.status == Status.PASS
    assert obs.data["identity_sha256"] == hashlib.sha256(text).hexdigest()
    assert obs.data["format"] == "text"
    assert obs.data["word_count"] == 5
    assert len(obs.data["canonical_sha256"]) == 64


def test_canonical_collapses_whitespace_and_normalises():
    a = CaptionOrgan().observe(b"Hello,   world!\n")[0]
    b = CaptionOrgan().observe(b"  Hello, world!  ")[0]
    assert a.data["identity_sha256"] != b.data["identity_sha256"]  # raw bytes differ
    assert a.data["canonical_sha256"] == b.data["canonical_sha256"]  # same canonical text


def test_canonical_differs_on_changed_text():
    a = CaptionOrgan().observe(b"the cat sat")[0]
    b = CaptionOrgan().observe(b"the dog sat")[0]
    assert a.data["canonical_sha256"] != b.data["canonical_sha256"]


def test_case_is_preserved():
    a = CaptionOrgan().observe(b"Yes")[0]
    b = CaptionOrgan().observe(b"yes")[0]
    assert a.data["canonical_sha256"] != b.data["canonical_sha256"]  # case is meaningful


def test_non_utf8_fails_closed():
    obs = CaptionOrgan().observe(b"\xff\xfe\x80not text")[0]
    assert obs.status == Status.UNVERIFIED
    assert obs.data["canonical_sha256"] is None
    assert obs.data["identity_sha256"] == hashlib.sha256(b"\xff\xfe\x80not text").hexdigest()


def test_canonical_caption_function():
    assert canonical_caption("  a\t b\n c  ") == "a b c"


def test_utf8_bom_is_canonically_equivalent():
    # a Windows .srt/.vtt BOM must not make the same caption text DRIFT
    plain = CaptionOrgan().observe("Hello, world!".encode("utf-8"))[0]
    bommed = CaptionOrgan().observe(b"\xef\xbb\xbf" + "Hello, world!".encode("utf-8"))[0]
    assert plain.data["identity_sha256"] != bommed.data["identity_sha256"]  # raw bytes differ
    assert plain.data["canonical_sha256"] == bommed.data["canonical_sha256"]  # BOM stripped


def test_bom_only_caption_has_zero_words():
    obs = CaptionOrgan().observe(b"\xef\xbb\xbf")[0]
    assert obs.data["word_count"] == 0


def test_missing_path_is_unverified(tmp_path):
    obs = CaptionOrgan().observe(tmp_path / "nope.srt")[0]
    assert obs.status == Status.UNVERIFIED and obs.data["decoded"] is False


def test_reads_from_path(tmp_path):
    p = tmp_path / "cue.txt"
    p.write_bytes(b"line one")
    obs = CaptionOrgan().observe(p)[0]
    assert obs.data["word_count"] == 2 and obs.status == Status.PASS


def test_baseline_matches_reformatted_caption_via_canonical_rung():
    # the caption canonical_sha256 plugs into baseline memory's canonical rung:
    # a whitespace-different but same-text caption is a MATCH.
    b = Baseline()
    b.pin(CaptionOrgan().observe(b"Hello, world!")[0])
    same = b.check(CaptionOrgan().observe(b"  Hello,   world!  ")[0])
    assert same.verdict == "MATCH"
    changed = b.check(CaptionOrgan().observe(b"Goodbye, world!")[0])
    assert changed.verdict == "DRIFT"


def test_selftest_passes():
    result = CaptionOrgan().selftest()
    assert result.passed, result.to_dict()
    assert len(result.checks) >= 6


def test_organ_does_not_mutate_input_file(tmp_path):
    p = tmp_path / "cue.txt"
    p.write_bytes(b"caption text")
    before = p.read_bytes()
    CaptionOrgan().observe(p)
    assert p.read_bytes() == before  # inert

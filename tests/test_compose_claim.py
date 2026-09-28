"""Native composition test: the gather -> chorus -> crucible claim-verification
pipeline runs end to end and binds all three stage fingerprints into a re-derivable
bundle.

The peer lanes are editable installs across this workspace; the shim below makes their
src importable so the test runs against the real lane code, not a stub. If a lane is not
importable at all, the test is skipped with a clear reason rather than failing spuriously.
"""
import pathlib
import sys

import pytest

for _p in ("gather", "chorus", "crucible"):
    _src = pathlib.Path(f"C:/dev/public/{_p}/src")
    if _src.is_dir() and str(_src) not in sys.path:
        sys.path.insert(0, str(_src))

from harness import compose_claim as cc  # noqa: E402

CORPUS = [
    {"kind": "comment", "id": "a", "ref": "v1", "text": "the sound design is great", "meta": {"like_count": 20}},
    {"kind": "comment", "id": "b", "ref": "v1", "text": "loved the sound design too", "meta": {"like_count": 3}},
    {"kind": "comment", "id": "c", "ref": "v1", "text": "the plot was bad and slow", "meta": {"like_count": 9}},
]


def _run(claim_text, selector):
    try:
        return cc.run_claim_verification(CORPUS, claim_text, selector)
    except cc.CompositionUnavailable as exc:
        pytest.skip(str(exc))


def test_pipeline_binds_all_three_stages():
    b = _run("the corpus contains comment a", {"kind": "comment", "id": "a"})
    assert b.gather_receipts == 3 and b.gather_ok is True and len(b.gather_seal) == 64
    assert b.chorus_verifies is True and b.chorus_themes >= 1
    assert len(b.chorus_digest_sha) == 64 and len(b.bundle_sha) == 64


def test_present_receipt_is_match():
    b = _run("the corpus contains comment a", {"kind": "comment", "id": "a"})
    assert b.verdict_status == "MATCH" and b.verdict_deviation == 0.0


def test_absent_receipt_is_drift():
    b = _run("the corpus contains comment zzz", {"kind": "comment", "id": "zzz"})
    assert b.verdict_status == "DRIFT"


def test_bundle_reproducible():
    a = _run("the corpus contains comment a", {"kind": "comment", "id": "a"})
    b = _run("the corpus contains comment a", {"kind": "comment", "id": "a"})
    assert a.bundle_sha == b.bundle_sha and a.gather_seal == b.gather_seal

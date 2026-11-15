"""Tests for the perceive() read API and the selftest harness."""

from __future__ import annotations

from coherence_membrane.observation import Status
from coherence_membrane.organ import run_selftests
from coherence_membrane.perception import all_organs, default_organs, perceive


def test_perceive_collects_observations(make_png):
    png = make_png(4, 4, bytes(4 * 4 * 3))
    snap = perceive([png, b"not a png"], timestamp="2026-01-01T00:00:00+00:00")
    assert snap.timestamp == "2026-01-01T00:00:00+00:00"
    assert len(snap.observations) == 2
    assert len(snap.by_organ("visual-artifact")) == 2


def test_snapshot_serialisable(make_png):
    snap = perceive([make_png(2, 2, bytes(12))])
    d = snap.to_dict()
    assert "observations" in d and "timestamp" in d
    assert d["observations"][0]["organ"] == "visual-artifact"


def test_default_selftests_pass():
    report = run_selftests(default_organs())
    assert report["passed"], report


def test_empty_organ_list_does_not_pass():
    # fail-closed: a membrane with no organs is not "passing"
    report = run_selftests([])
    assert report["passed"] is False


def test_all_organs_over_mixed_subjects_does_not_crash(make_png):
    # perceive() with every organ over image bytes, JSON bytes, and a Frame must
    # never raise -- each organ perceives its modality and degrades on the rest.
    from coherence_membrane.capture import Frame, FrameDescriptor

    png = make_png(2, 2, bytes(12))
    frame = Frame(
        descriptor=FrameDescriptor(source_id="s", frame_index=0,
                                   width=2, height=2, pixel_format="bgra"),
        payload=bytes(2 * 2 * 4),
    )
    snap = perceive([png, b'{"a": 1}', frame], organs=all_organs())
    assert len(snap.observations) >= 1  # ran to completion, nothing raised
    assert snap.by_organ("structured-data")  # the JSON was perceived by its organ


def test_all_organs_over_alien_subjects_does_not_crash():
    # None/int/list are out of contract for every organ; perceive must not raise
    # (Path(subject) would TypeError) -- each non-raw organ degrades, raw skips.
    snap = perceive([None, 123, ["x"]], organs=all_organs())
    assert snap.observations  # produced observations, did not crash
    assert all(o.status == Status.UNVERIFIED for o in snap.observations)


def test_all_organs_survive_pathological_subjects():
    # totality holds even for a subject whose __fspath__ raises OSError and a
    # Frame whose read() raises a non-OSError -- every organ degrades, none crash.
    from coherence_membrane.capture import FrameDescriptor

    class _BadFspath:
        def __fspath__(self):
            raise OSError("fspath boom")

    class _BadFrame:
        descriptor = FrameDescriptor(source_id="s", frame_index=0, pixel_format="bgra")

        def read(self):
            raise ValueError("read boom")

    # an embedded-null path string: Path() succeeds but read_bytes() raises
    # ValueError (not OSError) -- must still degrade, not crash.
    snap = perceive([_BadFspath(), _BadFrame(), "foo\x00bar.png"], organs=all_organs())
    assert all(o.status == Status.UNVERIFIED for o in snap.observations)


def test_all_organs_count_and_selftests_pass():
    # tier-2 (11+quantity+distribution=13) + tier-3 cross-check + lra-verifier = 15,
    # + the L0 graph-verifier = 16, all selftests green
    organs = all_organs()
    assert len(organs) == 16
    assert run_selftests(organs)["passed"]

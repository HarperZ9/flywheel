"""Tests for the change-proportional, self-throttling continuity loop."""

from __future__ import annotations

from coherence_membrane.capture import Frame, FrameDescriptor, IterableFrameSource
from coherence_membrane.continuity import ResourceBudget, run_continuity
from coherence_membrane.phash import DRIFT, MATCH, UNVERIFIABLE


def _events(frames, **kw):
    return list(run_continuity(IterableFrameSource(frames, pixel_format="png"), **kw))


def test_identical_frames_are_cheap_match(make_png):
    png = make_png(8, 8, bytes((i * 3) % 256 for i in range(8 * 8 * 3)))
    events = _events([png, png, png])
    # First frame establishes the baseline (a change vs nothing); the rest are
    # MATCH via the cheap identity hash only (no decode/perceptual work).
    assert events[0].verdict == DRIFT
    assert [e.verdict for e in events[1:]] == [MATCH, MATCH]
    assert all(e.observation is None for e in events[1:])  # no full work at rest


def test_changed_frames_drift_with_distance(gradient_rgb):
    events = _events([gradient_rgb(invert=False), gradient_rgb(invert=True)])
    assert events[0].verdict == DRIFT  # baseline
    assert events[1].verdict == DRIFT
    assert events[1].distance is not None and events[1].distance > 0
    assert events[1].observation is not None


def test_budget_throttles_expensive_work(gradient_rgb):
    events = _events(
        [gradient_rgb(invert=False), gradient_rgb(invert=True)],
        budget=ResourceBudget(max_full_observations=1),
    )
    assert events[0].verdict == DRIFT and not events[0].throttled
    # Second change exceeds the full-observation budget -> throttled, fail-closed.
    assert events[1].verdict == UNVERIFIABLE
    assert events[1].throttled is True
    assert events[1].observation is None


def test_non_png_changes_are_identity_drift_only():
    events = _events([b"alpha", b"bravo"])
    assert events[0].verdict == DRIFT
    assert events[1].verdict == DRIFT
    assert all(e.distance is None for e in events)  # no perceptual hash for raw


def test_non_png_identical_is_match():
    events = _events([b"same", b"same"])
    assert events[0].verdict == DRIFT
    assert events[1].verdict == MATCH


def test_max_frames_bounds_the_loop(make_png):
    png = make_png(2, 2, bytes(12))
    events = _events([png, png, png, png], max_frames=2)
    assert len(events) == 2


def test_cadence_backoff_calls_sleeper(make_png):
    png = make_png(4, 4, bytes(4 * 4 * 3))
    sleeps: list[float] = []
    _events(
        [png, png, png],
        budget=ResourceBudget(min_interval_s=0.5),
        clock=lambda: 0.0,
        sleeper=sleeps.append,
    )
    # First frame sets the clock; the next two back off to honour the interval.
    assert sleeps == [0.5, 0.5]


def test_events_serialisable(make_png):
    png = make_png(2, 2, bytes(12))
    event = _events([png])[0]
    d = event.to_dict()
    assert d["verdict"] == DRIFT
    assert "observation" in d and "throttled" in d


# --- raw-frame fast path (no organ passed; the loop selects RawFrameOrgan) ----


def test_raw_frames_identical_are_cheap_match(raw_bgra_frame):
    f0, _, _, _ = raw_bgra_frame(8, 8, frame_index=0)
    f1, _, _, _ = raw_bgra_frame(8, 8, frame_index=1)  # identical pixels
    events = list(run_continuity(IterableFrameSource([f0, f1])))
    assert events[0].verdict == DRIFT  # baseline
    assert events[1].verdict == MATCH  # identity hash only, no perceptual work
    assert events[1].observation is None


def test_raw_frames_changed_drift_with_distance(raw_bgra_frame):
    f0, _, _, _ = raw_bgra_frame(16, 16, invert=False, frame_index=0)
    f1, _, _, _ = raw_bgra_frame(16, 16, invert=True, frame_index=1)
    events = list(run_continuity(IterableFrameSource([f0, f1])))
    assert events[1].verdict == DRIFT
    assert events[1].distance is not None and events[1].distance > 0
    # The full witnessed observation came from the raw organ, with no PNG encode.
    assert events[1].observation is not None
    assert events[1].observation.organ == "raw-frame"


class _CountingFrame:
    """A Frame-like that counts how many times the loop reads it."""

    def __init__(self, descriptor, payload):
        self.descriptor = descriptor
        self._payload = payload
        self.reads = 0

    def read(self):
        self.reads += 1
        return self._payload


class _OneShotSource:
    def __init__(self, frame):
        self._frame = frame

    def frames(self):
        yield self._frame


def test_loop_reads_each_source_frame_exactly_once():
    # Regression: the loop must read the source frame once (for cur_sha) and then
    # perceive the SAME bytes -- not re-read (a second disk hit / TOCTOU window for
    # path-backed frames). It hands the organ a wrapper carrying the read bytes.
    desc = FrameDescriptor(source_id="t", frame_index=0, width=4, height=4, pixel_format="bgra")
    cf = _CountingFrame(desc, bytes(4 * 4 * 4))
    list(run_continuity(_OneShotSource(cf)))
    assert cf.reads == 1


def test_degenerate_raw_frame_does_not_crash_the_loop(raw_bgra_frame):
    # A 0x0 raw frame must not take down an always-on loop (fail-closed).
    good, _, _, _ = raw_bgra_frame(8, 8, frame_index=0)
    bad = Frame(descriptor=FrameDescriptor(source_id="t", frame_index=1,
                                           width=0, height=0, pixel_format="bgra"),
                payload=bytes(8))
    events = list(run_continuity(IterableFrameSource([good, bad])))
    assert len(events) == 2  # survived the degenerate frame

"""Tests for temporal perception -- EventTrace over a continuity stream."""

from __future__ import annotations

import pytest

from coherence_membrane.continuity import ContinuityEvent
from coherence_membrane.events import DriftEpisode, EventTrace, trace_events
from coherence_membrane.phash import DRIFT, MATCH, UNVERIFIABLE


def _ev(verdict, distance=None):
    return {"verdict": verdict, "distance": distance}


def test_empty_stream():
    t = trace_events([])
    assert t.episodes == [] and t.total_events == 0 and t.longest_dwell == 0


def test_all_match_is_one_long_dwell_no_episodes():
    t = trace_events([_ev(MATCH)] * 5)
    assert t.episodes == []
    assert t.match_events == 5 and t.longest_dwell == 5


def test_single_drift_then_settle():
    t = trace_events([_ev(MATCH), _ev(DRIFT, 7), _ev(MATCH)])
    assert len(t.episodes) == 1
    e = t.episodes[0]
    assert e.start_index == 1 and e.end_index == 1 and e.length == 1
    assert e.peak_distance == 7 and e.settled_at == 2 and e.settled is True


def test_drift_run_peak_distance_and_settle():
    t = trace_events([_ev(DRIFT, 4), _ev(DRIFT, 18), _ev(DRIFT, 9), _ev(MATCH)])
    assert len(t.episodes) == 1
    e = t.episodes[0]
    assert e.start_index == 0 and e.end_index == 2 and e.length == 3
    assert e.peak_distance == 18 and e.settled_at == 3


def test_unverifiable_inside_episode_keeps_it_open():
    t = trace_events([_ev(DRIFT, 5), _ev(UNVERIFIABLE), _ev(DRIFT, 6), _ev(MATCH)])
    assert len(t.episodes) == 1
    e = t.episodes[0]
    assert e.start_index == 0 and e.end_index == 2 and e.peak_distance == 6
    assert e.settled_at == 3
    assert t.unverifiable_events == 1


def test_unsettled_episode_at_stream_end():
    t = trace_events([_ev(MATCH), _ev(DRIFT, 3)])
    assert len(t.episodes) == 1
    e = t.episodes[0]
    assert e.settled_at is None and e.settled is False
    assert t.unsettled_episodes == [e]


def test_two_episodes():
    t = trace_events([_ev(DRIFT, 2), _ev(MATCH), _ev(DRIFT, 5), _ev(MATCH)])
    assert len(t.episodes) == 2
    assert t.episodes[0].settled_at == 1 and t.episodes[1].settled_at == 3


def test_unverifiable_only_is_not_an_episode():
    t = trace_events([_ev(UNVERIFIABLE), _ev(UNVERIFIABLE)])
    assert t.episodes == []
    assert t.unverifiable_events == 2 and t.drift_events == 0


def test_longest_dwell_resets_on_change():
    t = trace_events([_ev(MATCH), _ev(MATCH), _ev(DRIFT, 1), _ev(MATCH)])
    assert t.longest_dwell == 2  # the leading run, not the trailing single


def test_peak_distance_none_when_unquantified():
    t = trace_events([_ev(DRIFT, None), _ev(MATCH)])
    assert t.episodes[0].peak_distance is None


def test_accepts_continuity_events_and_strings():
    events = [
        ContinuityEvent(0, "s", DRIFT, 4, None, False, "n"),
        ContinuityEvent(1, "s", MATCH, 0, None, False, "n"),
    ]
    t = trace_events(events)
    assert len(t.episodes) == 1 and t.episodes[0].peak_distance == 4
    # bare verdict strings (distance unknown) also work
    t2 = trace_events([DRIFT, MATCH])
    assert len(t2.episodes) == 1 and t2.episodes[0].peak_distance is None


def test_unknown_verdict_raises():
    with pytest.raises(ValueError):
        trace_events([_ev("WOBBLE")])


def test_trace_serialisable():
    d = trace_events([_ev(DRIFT, 3), _ev(MATCH)]).to_dict()
    assert d["episodes"][0]["settled"] is True
    assert d["drift_events"] == 1 and d["match_events"] == 1

"""Presence-only rosters cannot establish runtime readiness."""
from harness.desktop_status import desktop_status


def test_declared_roster_is_unprobed_not_degraded():
    result = desktop_status({"n_lanes": 15, "by_status": {"declared": 15}})
    assert result["status"] == "ok"
    assert result["lane_readiness"] == "unprobed"
    assert result["lanes_declared"] == 15
    assert result["lanes_live"] == 0


def test_missing_and_stale_are_observed_problems():
    for status in ("missing", "stale"):
        result = desktop_status({"n_lanes": 15,
                                 "by_status": {"declared": 14, status: 1}})
        assert result["status"] == "degraded"
        assert result[f"lanes_{status}"] == 1
        assert result["lanes_declared"] == 14


def test_complete_live_roster_and_empty_registry_are_distinct():
    live = desktop_status({"n_lanes": 2, "by_status": {"live": 2}})
    empty = desktop_status({"n_lanes": 0, "by_status": {}})
    assert live["lane_readiness"] == "probed"
    assert empty["lane_readiness"] == "empty"
    missing = desktop_status({"n_lanes": 2, "by_status": {"missing": 2}})
    assert missing["lane_readiness"] == "unavailable"
    partial = desktop_status({"n_lanes": 2, "by_status": {"live": 1, "missing": 1}})
    assert partial["lane_readiness"] == "partial"


def test_incomplete_or_invalid_roster_never_claims_readiness():
    for roster in ({}, {"n_lanes": True, "by_status": {}},
                   {"n_lanes": 3, "by_status": {"live": 2}},
                   {"n_lanes": 3, "by_status": {"live": 3, "declared": 1}},
                   {"n_lanes": 3, "by_status": {"declared": "3"}}):
        assert desktop_status(roster)["lane_readiness"] == "unknown"

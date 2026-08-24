"""desktop-status/v1 -- typed connection facts for the desktop shell.

The shell must distinguish online, degraded, incompatible, and honest
zero states instead of one boolean alive flag. The route is read-only
and serves fixed facts: schema, status, api compatibility, and the lane
summary. Missing roster fields degrade to zeros; they never crash.
"""
from harness.desktop_status import API_VERSION, SCHEMA, desktop_status


def _roster(live, total):
    return {"n_lanes": total, "by_status": {"live": live}}


def test_schema_is_versioned_and_stable():
    assert SCHEMA == "flywheel.desktop-status/v1"
    doc = desktop_status(_roster(3, 3))
    assert doc["schema"] == SCHEMA


def test_full_roster_reads_online():
    doc = desktop_status(_roster(3, 3))
    assert doc["status"] == "ok"
    assert doc["lanes_live"] == 3
    assert doc["lanes_total"] == 3
    assert doc["compatible"] is True


def test_partial_roster_reads_degraded():
    doc = desktop_status(_roster(2, 3))
    assert doc["status"] == "degraded"


def test_zero_lanes_is_an_honest_ok_not_a_degraded():
    doc = desktop_status(_roster(0, 0))
    assert doc["status"] == "ok"
    assert doc["lanes_total"] == 0


def test_missing_roster_fields_degrade_to_zeros():
    doc = desktop_status({})
    assert doc["status"] == "ok"
    assert doc["lanes_live"] == 0
    assert doc["lanes_total"] == 0
    assert doc["status"] != "degraded"


def test_newer_client_api_reports_incompatible():
    doc = desktop_status(_roster(3, 3), client_api=API_VERSION + 1)
    assert doc["compatible"] is False
    assert doc["status"] == "incompatible"


def test_api_version_is_served_for_the_client_to_compare():
    doc = desktop_status(_roster(1, 1))
    assert doc["api_version"] == API_VERSION
    assert isinstance(API_VERSION, int)

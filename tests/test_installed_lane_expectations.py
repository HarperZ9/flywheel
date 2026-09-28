"""The installed-app lane step turns red when a lane leaves its expected row.

Acceptance audit of run 36302181098, findings F1 to F4, and the product-truth
review of 1.1.0, PT-2: the step exited 0 on BELOW_BAR, so a run with all 17
lanes below the bar, or with an engine whose API answered nothing, stayed
green; a held lane ignored its failed checks; and a tier refusal passed on any
non-200 answer, a dead engine included. The green job said nothing about the
lane count the notes and README carry.

Now every lane has an expected row (packaging/installed-lane-expectations.json),
the step exits 1 when any lane departs from it in either direction or a held
lane fails a check, and a tier refusal must be a 403 that says the governance
gate denied it.
"""
from __future__ import annotations

import pytest

from scripts import installed_app_lane_acceptance as acceptance
from scripts import installed_lane_expectations as expected
from scripts import installed_lane_verdict as verdict
from scripts.installed_lane_cases import CASES, DENIED, Check, LaneCase, st
from harness.lane_tool_policy import tool_policy


def _lanes(failing: dict[str, tuple[str, ...]] | None = None, *, everything_fails=False):
    failing = failing or {}
    rows = {}
    for lane, case in CASES.items():
        outcomes = {}
        for check in case.checks:
            bad = everything_fails or check.name in failing.get(lane, ())
            outcomes[check.name] = verdict.Outcome("fail" if bad else "pass")
        rows[lane] = verdict.lane_verdict(case, outcomes)
    return rows


def _receipt(lanes, guards=None):
    guards = guards or {"fresh_settled": True}
    return {"summary": verdict.summary(lanes, guards), "lanes": lanes, "guards": guards}


def test_every_lane_has_exactly_one_expected_row():
    assert set(expected.load()) == set(CASES)


def test_the_run_the_notes_count_from_matches_its_rows_and_exits_0():
    lanes = _lanes({"index": ("fresh_map_needs_git",)})
    judged = expected.judge(lanes)
    assert judged == {"matches": True, "departures": []}
    assert acceptance.exit_code(_receipt(lanes)) == 0


def test_every_lane_below_the_bar_exits_1():
    lanes = _lanes(everything_fails=True)
    judged = expected.judge(lanes)
    assert judged["matches"] is False
    assert {d["lane"] for d in judged["departures"]} == set(CASES)
    assert acceptance.exit_code(_receipt(lanes)) == 1


def test_telos_is_expected_at_class_now_that_it_ships():
    """telos 0.4.2 ended the hold, so its row expects AT_CLASS: a run where the
    lane stayed held, or failed any of its checks, departs."""
    rows = expected.load()
    assert rows["telos"]["verdict"] == "AT_CLASS" and not rows["telos"].get("failed")
    assert not any(row["verdict"] == "HELD" for row in rows.values())
    for check in CASES["telos"].checks:
        lanes = _lanes({"index": ("fresh_map_needs_git",), "telos": (check.name,)})
        assert [d["lane"] for d in expected.judge(lanes)["departures"]] == ["telos"], check.name
        assert acceptance.exit_code(_receipt(lanes)) == 1
    held = _lanes({"index": ("fresh_map_needs_git",)})
    held["telos"] = {**held["telos"], "verdict": "HELD", "failed": []}
    assert [d["lane"] for d in expected.judge(held)["departures"]] == ["telos"]


def test_a_held_lane_with_a_failed_check_exits_1():
    # No lane is held today; the rule still has to hold for one that is.
    case = LaneCase("held-lane", "B", "held", "a stated hold",
                    (st("fresh", "cannot_launch", code="lane_held"),))
    rows = {**expected.load(), "held-lane": {"verdict": "HELD", "failed": []}}
    lanes = _lanes({"index": ("fresh_map_needs_git",)})
    lanes["held-lane"] = verdict.lane_verdict(case, {"fresh_state": verdict.Outcome("pass")})
    assert expected.judge(lanes, rows) == {"matches": True, "departures": []}
    lanes["held-lane"] = verdict.lane_verdict(case, {"fresh_state": verdict.Outcome("fail")})
    assert lanes["held-lane"]["verdict"] == "HELD"
    departures = expected.judge(lanes, rows)["departures"]
    assert [d["lane"] for d in departures] == ["held-lane"]
    receipt = {**_receipt(lanes), "expected": expected.judge(lanes, rows)}
    assert acceptance.exit_code(receipt) == 1


@pytest.mark.parametrize("failing", [
    {},                                                      # index now at class: a better
    {"index": ("fresh_map_needs_git", "setup_map")},         # or a worse departure
    {"index": ("fresh_map_needs_git",), "gather": ("fresh_main",)},
])
def test_a_departure_in_either_direction_exits_1(failing):
    lanes = _lanes(failing)
    assert expected.judge(lanes)["matches"] is False
    assert acceptance.exit_code(_receipt(lanes)) == 1


def test_a_broken_guard_still_exits_1():
    lanes = _lanes({"index": ("fresh_map_needs_git",)})
    assert acceptance.exit_code(_receipt(lanes, {"install_folder_unchanged": False})) == 1


def _denied_check():
    return Check("x_refused", "fresh", "call", tool="judge", expect_status=DENIED)


@pytest.mark.parametrize("status,body,result", [
    (403, {"error": "governance gate: ...", "governance_denied": True}, "pass"),
    (403, {"error": "forbidden"}, "fail"),                   # a 403 that is not the gate
    (404, {"error": "no such tool"}, "fail"),
    (500, {"error": "boom"}, "fail"),
    (0, {"code": "TRANSPORT_ERROR"}, "fail"),                # the engine is gone
])
def test_a_tier_refusal_must_be_the_governance_gate(status, body, result):
    assert verdict.evaluate_call(_denied_check(), status, body).result == result


def test_every_refusal_check_names_a_tool_the_policy_knows_and_expects_a_reason():
    for lane, case in CASES.items():
        for check in case.checks:
            if check.kind != "call" or check.expect_status == 200:
                continue
            entry = tool_policy(lane, check.tool)
            assert entry is not None, (lane, check.tool)
            assert check.expect_status == DENIED or check.expect_code, (lane, check.name)
            if check.expect_status == DENIED:
                assert entry.tier == "T2" and check.tier == "T1", (lane, check.name)


def test_the_receipt_limits_follow_where_the_check_ran():
    """Acceptance audit F7: the CI receipt said the acceptance installer differs
    from the release installer, which is false on CI (it builds and accepts the
    release installer) and named "the build machine" for a hosted runner."""
    ci = " ".join(verdict.does_not_prove({"GITHUB_ACTIONS": "true"}))
    local = " ".join(verdict.does_not_prove({}))
    assert "AppId" not in ci and "GitHub-hosted" in ci and "administrator" in ci
    assert "AppId" in local and "build machine" in local
    for text in (ci, local):
        for phrase in ("provider", "model quality", "bulletin write", "actuation",
                       "consumer Windows"):
            assert phrase in text

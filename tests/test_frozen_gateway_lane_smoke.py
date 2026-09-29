"""The frozen lane smoke checks a real reply, not an exit code.

Each case runs a real child process over stdio: a child that exits, a
forum-shaped crash, and a small MCP server that replies. The old smoke counted
any exit other than 2 as admitted, so forum's crash printed PASS in 1.0.4.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

from harness.lanes_registry import LANES
from harness.mcp_client import LaunchSpec
from scripts import check_frozen_gateway
from scripts import frozen_gateway_lane_smoke as smoke
from scripts.lane_smoke_fixtures import FIXTURES, NO_FIXTURE

FAKE_SERVER = r'''
import json, sys
replies = json.loads(sys.argv[1])
for line in sys.stdin:
    msg = json.loads(line)
    if "id" not in msg:
        continue
    method = msg["method"]
    if method == "initialize":
        result = {"protocolVersion": "2024-11-05", "capabilities": {},
                  "serverInfo": {"name": "fake", "version": "0"}}
    elif method == "tools/list":
        result = {"tools": [{"name": n, "inputSchema": {"type": "object"}}
                            for n in replies]}
    else:
        name = msg["params"]["name"]
        result = {"content": [{"type": "text", "text": json.dumps(replies[name])}],
                  "isError": False}
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg["id"],
                                 "result": result}) + "\n")
    sys.stdout.flush()
'''

FORUM_CRASH = (
    "import sys; sys.stderr.write('FileNotFoundError: C:/Users/someone/_internal/"
    "forum/manifests/default-roster.toml\\n'); sys.exit(1)")

PLEXUS_REPLIES = {"plexus.status": {"ok": True},
                  "plexus_route": {"connected": True, "hops": 1}}


def _fake(replies: dict, allowed: tuple[str, ...]) -> smoke.LanePlan:
    launch = LaunchSpec((sys.executable, "-c", FAKE_SERVER, json.dumps(replies)),
                        allowed_tools=allowed)
    return smoke.LanePlan(launch, "plexus.status")


def _crash(code: str) -> smoke.LanePlan:
    return smoke.LanePlan(LaunchSpec((sys.executable, "-c", code)), "forum.status")


def _rows(**lanes: str) -> dict:
    return {lane: {"expected": level, "bar": "A"} for lane, level in lanes.items()}


def _run(plans: dict, rows: dict, tmp_path: Path) -> dict:
    return smoke.run_lane_smoke(plans, rows, home=tmp_path, timeout=20)


def test_child_that_exits_1_fails(tmp_path):
    plans = {"forum": _crash("import sys; sys.exit(1)")}
    receipt = _run(plans, _rows(forum="health"), tmp_path)
    assert receipt["lanes"]["forum"]["level"] == "cannot_launch"
    assert receipt["lanes"]["forum"]["exit_code"] == 1
    assert receipt["verdict"] == "FAIL"
    assert receipt["failures"] == ["forum"]


def test_forum_shaped_crash_fails_and_leaks_no_stderr(tmp_path):
    receipt = _run({"forum": _crash(FORUM_CRASH)}, _rows(forum="health"), tmp_path)
    assert receipt["verdict"] == "FAIL"
    assert receipt["lanes"]["forum"]["reason"] == "initialize_failed"
    assert "default-roster" not in json.dumps(receipt)


def test_forum_shaped_crash_is_never_pass_with_todays_rows(tmp_path):
    # WP2 froze forum's package data and raised its row to health, so the
    # 1.0.4 crash is now a regression and fails the smoke outright.
    rows = smoke.load_expectations()
    plans = {"forum": _crash(FORUM_CRASH)}
    receipt = _run(plans, {"forum": rows["forum"]}, tmp_path)
    assert receipt["lanes"]["forum"]["level"] == "cannot_launch"
    assert receipt["verdict"] == "FAIL"
    assert receipt["failures"] == ["forum"]


def test_replying_fake_passes(tmp_path):
    plans = {"plexus": _fake(PLEXUS_REPLIES, ("plexus.status", "plexus_route"))}
    receipt = _run(plans, _rows(plexus="main"), tmp_path)
    assert receipt["lanes"]["plexus"] == {
        "level": "main", "expected": "main", "bar": "A", "reason": "ok",
        "outside_writes": []}
    assert receipt["verdict"] == "PASS"
    assert receipt["below_bar"] == [] and receipt["failures"] == []


def test_lane_below_bar_is_below_bar_expected_not_pass(tmp_path):
    plans = {"plexus": _fake(PLEXUS_REPLIES, ("plexus.status",))}
    receipt = _run(plans, _rows(plexus="health"), tmp_path)
    assert receipt["lanes"]["plexus"]["level"] == "health"
    assert receipt["lanes"]["plexus"]["reason"] == "main_not_admitted"
    assert receipt["verdict"] == "BELOW_BAR_EXPECTED"
    assert receipt["below_bar"] == ["plexus"]


def test_wrong_main_reply_stays_at_health(tmp_path):
    replies = {"plexus.status": {"ok": True}, "plexus_route": {"connected": False}}
    plans = {"plexus": _fake(replies, ("plexus.status", "plexus_route"))}
    receipt = _run(plans, _rows(plexus="main"), tmp_path)
    assert receipt["lanes"]["plexus"]["level"] == "health"
    assert receipt["lanes"]["plexus"]["reason"] == "main_assertion_failed"
    assert receipt["verdict"] == "FAIL"


def test_lane_above_expected_fails_until_its_row_is_raised(tmp_path):
    plans = {"plexus": _fake(PLEXUS_REPLIES, ("plexus.status", "plexus_route"))}
    receipt = _run(plans, _rows(plexus="health"), tmp_path)
    assert receipt["verdict"] == "FAIL"
    assert receipt["failures"] == ["plexus"]


def test_lane_without_a_frozen_launch_is_measured_as_such(tmp_path):
    receipt = _run({}, _rows(bulletin="no_frozen_launch"), tmp_path)
    assert receipt["lanes"]["bulletin"]["level"] == "no_frozen_launch"
    assert receipt["verdict"] == "BELOW_BAR_EXPECTED"


def test_built_lane_without_an_expectation_row_fails(tmp_path):
    plans = {"plexus": _fake(PLEXUS_REPLIES, ("plexus.status",))}
    receipt = _run(plans, {}, tmp_path)
    assert receipt["verdict"] == "FAIL"
    assert receipt["failures"] == ["plexus"]


def test_expectations_cover_every_registry_lane():
    rows = smoke.load_expectations()
    assert set(rows) == set(LANES)
    for lane, row in rows.items():
        assert {"expected", "bar"} <= set(row) <= {"expected", "bar", "reason"}, lane
        assert row["expected"] in smoke.LEVELS, lane
        assert row["bar"] in smoke.CLASSES, lane


def test_every_bundled_lane_has_a_fixture():
    rows = smoke.load_expectations()
    bundled = {lane for lane, row in rows.items()
               if row["expected"] != "no_frozen_launch"}
    assert bundled <= set(FIXTURES) | set(NO_FIXTURE)
    # An exemption states why and never shadows a real fixture.
    assert not set(NO_FIXTURE) & set(FIXTURES)
    assert all(len(reason) > 40 for reason in NO_FIXTURE.values())


@pytest.mark.parametrize("lane", sorted(FIXTURES))
def test_fixture_rejects_empty_and_error_replies(lane):
    check = FIXTURES[lane].check
    assert check({}) is False
    assert check({"error": "boom"}) is False
    assert check("error: boom") is False


def _main(monkeypatch, tmp_path, lane_receipt=None, failure=None):
    def fake_check(executable, expected_version, receipt):
        if failure:
            raise RuntimeError(failure)
        receipt["lane_smoke"] = lane_receipt

    monkeypatch.setattr(check_frozen_gateway, "check", fake_check)
    out = tmp_path / "receipt.json"
    monkeypatch.setattr(sys, "argv", [
        "check_frozen_gateway.py", "--executable", str(tmp_path / "x.exe"),
        "--expected-version", "1.0.4", "--receipt", str(out)])
    code = check_frozen_gateway.main()
    return code, json.loads(out.read_text(encoding="utf-8"))


def test_release_receipt_never_prints_pass_below_bar(monkeypatch, tmp_path):
    code, receipt = _main(monkeypatch, tmp_path,
                          {"verdict": "BELOW_BAR_EXPECTED", "below_bar": ["forum"]})
    assert receipt["verdict"] == "BELOW_BAR_EXPECTED"
    assert code == 0


def test_release_receipt_prints_pass_only_at_bar(monkeypatch, tmp_path):
    code, receipt = _main(monkeypatch, tmp_path, {"verdict": "PASS", "below_bar": []})
    assert (code, receipt["verdict"]) == (0, "PASS")


def test_release_receipt_holds_on_lane_regression(monkeypatch, tmp_path):
    code, receipt = _main(monkeypatch, tmp_path, failure="LANE_SMOKE_FAIL:forum")
    assert (code, receipt["verdict"]) == (1, "HOLD")
    assert receipt["failure"] == "LANE_SMOKE_FAIL:forum"

"""The installed-app lane acceptance judges what it measured, and nothing else.

These cases pin the pure parts of ``scripts/installed_app_lane_acceptance.py``:
the stripped engine environment, the settle and D1 guards, the install-folder
diff, the per-lane check table against the tool policy, the per-lane verdict
(a lane is in its class only when every check passed; a held lane is below the
bar; a host fact that hides a state is ``not_measurable``, not a pass), and the
receipt scrub that keeps the gateway token out of the file.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from harness.lane_tool_policy import HELD_LANES, admitted_tools, main_tools, tool_policy
from harness.lanes_registry import LANES
from scripts import installed_lane_engine as engine
from scripts import installed_lane_verdict as verdict
from scripts.installed_lane_cases import CASES, DENIED, REFUSED, Check, LaneCase, st


def test_profile_env_is_stripped_and_throwaway(tmp_path, monkeypatch):
    monkeypatch.setenv("WP11_PLANTED_API_KEY", "sk-planted-value")
    env = engine.profile_env(tmp_path, git=None, systemroot=r"C:\Windows")
    assert env["PATH"] == r"C:\Windows\System32"
    assert env["FLYWHEEL_GIT"] == "none"
    assert "FLYWHEEL_NODE" not in env
    assert "WP11_PLANTED_API_KEY" not in env
    for name in ("FLYWHEEL_HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP"):
        assert Path(env[name]).is_relative_to(tmp_path), name
    assert set(env) <= engine.ENV_NAMES


def test_profile_env_points_git_at_the_given_install(tmp_path):
    env = engine.profile_env(tmp_path, git=r"C:\Program Files\Git\cmd\git.exe",
                             systemroot=r"C:\Windows")
    assert env["FLYWHEEL_GIT"] == r"C:\Program Files\Git\cmd\git.exe"
    assert env["PATH"] == r"C:\Windows\System32"


def test_tree_changes_names_added_removed_and_changed(tmp_path):
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    before = engine.tree_snapshot(tmp_path)
    (tmp_path / "a.txt").write_text("aa", encoding="utf-8")
    (tmp_path / "b.txt").unlink()
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.db").write_text("c", encoding="utf-8")
    changes = engine.tree_changes(before, engine.tree_snapshot(tmp_path))
    assert changes == {"added": ["sub/c.db"], "removed": ["b.txt"], "changed": ["a.txt"]}
    assert engine.tree_changes(before, before) == {"added": [], "removed": [], "changed": []}


def _roster(**states):
    return {"lanes": [{"name": k, "state": v, "code": None} for k, v in states.items()]}


def test_wait_settled_needs_a_quiet_period():
    rosters = iter([_roster(gather="not_checked"), _roster(gather="ready")]
                   + [_roster(gather="ready")] * 20)
    now = [0.0]
    out = engine.wait_settled(lambda: next(rosters), quiet_s=6, limit_s=60,
                              clock=lambda: now[0],
                              sleep=lambda s: now.__setitem__(0, now[0] + s))
    assert out["settled"] is True
    assert engine.states_of(out["roster"]) == {"gather": ("ready", None)}


def test_wait_settled_reports_a_roster_that_never_settles():
    flip = iter(["ready", "limited"] * 100)
    now = [0.0]
    out = engine.wait_settled(lambda: _roster(gather=next(flip)), quiet_s=6, limit_s=20,
                              clock=lambda: now[0],
                              sleep=lambda s: now.__setitem__(0, now[0] + s))
    assert out["settled"] is False


def test_d1_guard_compares_states_and_codes():
    same = [_roster(gather="ready", index="limited")] * 3
    assert engine.d1_unchanged(same) is True
    moved = same[:2] + [_roster(gather="not_checked", index="limited")]
    assert engine.d1_unchanged(moved) is False


def test_cases_cover_every_registry_lane():
    assert set(CASES) == set(LANES)


def test_every_call_check_names_a_tool_the_policy_knows():
    for lane, case in CASES.items():
        for check in case.checks:
            if check.kind != "call" or check.expect_status != 200:
                continue
            entry = tool_policy(lane, check.tool)
            assert entry is not None and not entry.not_in_build, (lane, check.tool)
            assert entry.tier == check.tier, (lane, check.tool)
            if entry.tier == "T1":
                assert check.tool in admitted_tools(lane), (lane, check.tool)


def test_every_lane_with_a_main_tool_runs_one_main_call():
    for lane, case in CASES.items():
        mains = set(main_tools(lane))
        if not mains:
            continue
        ran = {c.tool for c in case.checks if c.kind == "call" and c.expect_status == 200}
        assert ran & mains, lane


def _outcomes(case, result="pass"):
    return {c.name: verdict.Outcome(result, {}) for c in case.checks}


def test_a_lane_with_every_check_passing_is_in_its_class():
    case = CASES["crucible"]
    row = verdict.lane_verdict(case, _outcomes(case))
    assert row["verdict"] == "AT_CLASS" and row["class_measured"] == case.class_expected


def test_one_failed_check_puts_the_lane_below_the_bar_with_its_reason():
    case = CASES["index"]
    outcomes = _outcomes(case)
    name = case.checks[-1].name
    outcomes[name] = verdict.Outcome("fail", {"status": 409, "code": "LANE_SETUP_REQUIRED"})
    row = verdict.lane_verdict(case, outcomes)
    assert row["verdict"] == "BELOW_BAR" and row["class_measured"] is None
    assert row["failed"] == [{"check": name, "status": 409, "code": "LANE_SETUP_REQUIRED"}]


def test_a_check_that_never_ran_is_not_a_pass():
    case = CASES["canon"]
    outcomes = _outcomes(case)
    outcomes.pop(case.checks[-1].name)
    assert verdict.lane_verdict(case, outcomes)["verdict"] == "BELOW_BAR"


def test_not_measurable_is_listed_and_does_not_fail_the_lane():
    case = CASES["relay"]
    outcomes = _outcomes(case)
    confounded = next(c for c in case.checks if c.confound)
    outcomes[confounded.name] = verdict.Outcome("not_measurable", {"host": "model_server"})
    row = verdict.lane_verdict(case, outcomes)
    assert row["verdict"] == "AT_CLASS" and row["not_measurable"] == [confounded.name]


def _held_case() -> LaneCase:
    # No lane is held today (telos 0.4.2 ended its hold); the verdict for one
    # still has to hold, so the case is built here.
    return LaneCase("held-lane", "B", "held", "a stated hold",
                    (st("fresh", "cannot_launch", code="lane_held"),))


def test_a_held_lane_is_below_the_bar():
    case = _held_case()
    row = verdict.lane_verdict(case, _outcomes(case))
    assert row["verdict"] == "HELD" and row["class_measured"] is None
    assert not any(c.class_expected == "held" for c in CASES.values()
                   if c.lane not in HELD_LANES)


def test_summary_passes_only_when_every_lane_is_in_its_class():
    rows = {"a": {"verdict": "AT_CLASS", "class_measured": "A"},
            "b": {"verdict": "AT_CLASS", "class_measured": "B"}}
    assert verdict.summary(rows)["verdict"] == "PASS"
    rows["c"] = {"verdict": "HELD", "class_measured": None}
    out = verdict.summary(rows)
    assert out["verdict"] == "BELOW_BAR" and out["below_bar"] == ["c"]
    assert out["by_class"] == {"A": 1, "B": 1}


def test_evaluate_state_matches_the_allowed_states_and_code():
    check = Check("s", "fresh", "state", states=("cannot_launch",), code="lane_held")
    good = {"state": "cannot_launch", "code": "lane_held"}
    assert verdict.evaluate_state(check, good, host={}).result == "pass"
    assert verdict.evaluate_state(check, {**good, "code": "x"}, host={}).result == "fail"
    assert verdict.evaluate_state(check, None, host={}).result == "fail"


def test_evaluate_state_is_not_measurable_when_the_host_hides_it():
    check = Check("s", "fresh", "state", states=("needs_setup",), confound="model_server")
    row = {"state": "ready", "code": None}
    assert verdict.evaluate_state(check, row, host={"model_server": True}).result == \
        "not_measurable"
    assert verdict.evaluate_state(check, row, host={"model_server": False}).result == "fail"


def test_evaluate_call_checks_status_code_and_assertion():
    ok = Check("c", "fresh", "call", tool="score", assert_=lambda b: b.get("n") == 1)
    assert verdict.evaluate_call(ok, 200, {"n": 1}).result == "pass"
    assert verdict.evaluate_call(ok, 200, {"n": 2}).result == "fail"
    refused = Check("r", "fresh", "call", tool="x", expect_status=409,
                    expect_code="LANE_SETUP_REQUIRED")
    assert verdict.evaluate_call(refused, 409, {"code": "LANE_SETUP_REQUIRED"}).result == "pass"
    assert verdict.evaluate_call(refused, 200, {"n": 1}).result == "fail"


def test_evaluate_tools_needs_each_main_tool_admitted_with_a_schema():
    listing = {"tools": [{"name": "score", "admitted": True, "main": True,
                          "inputSchema": {"type": "object"}},
                         {"name": "check", "admitted": True, "main": True,
                          "inputSchema": {"type": "object"}}]}
    assert verdict.evaluate_tools("articulate", 200, listing).result == "pass"
    listing["tools"][1].pop("inputSchema")
    assert verdict.evaluate_tools("articulate", 200, listing).result == "fail"
    assert verdict.evaluate_tools("articulate", 503, {"code": "LANE_CANNOT_LAUNCH"}).result \
        == "fail"


def test_redact_replaces_a_secret_anywhere_and_counts_it():
    value = {"a": ["x tok-123 y", {"b": "tok-123"}], "c": 1}
    clean, hits = verdict.redact(value, ("tok-123",))
    assert hits == 2 and "tok-123" not in repr(clean)
    with pytest.raises(ValueError):
        verdict.redact(value, ("",))


def test_the_receipt_states_what_it_does_not_prove():
    text = " ".join(verdict.DOES_NOT_PROVE)
    for phrase in ("provider", "model quality", "bulletin write", "actuation",
                   "consumer Windows"):
        assert phrase in text


def test_model_lane_assertions_need_the_stub_reply_and_a_verified_run():
    local = next(c for c in CASES["local-model"].checks if c.name == "setup_main")
    assert local.stub_hit is True
    assert local.assert_({"final": "ok", "steps": 1, "verified": True}) is True
    assert local.assert_({"final": "ok", "verified": False}) is False
    assert local.assert_({"final": "ok", "verified": True,
                          "error": "WORKSPACE_PROTECTED"}) is False


def test_index_map_needs_a_repository_it_could_read():
    check = next(c for c in CASES["index"].checks if c.name == "setup_map")
    assert check.assert_({"metadata_status": "ok", "repo_count": 1}) is True
    assert check.assert_({"metadata_status": "ok", "repo_count": 0}) is False


def test_the_telos_checks_cover_each_tier_with_tools_telos_has():
    """telos 0.4.2 at class A: the catalog runs at T1, workflow is refused at T1
    and answers at T2 with its own envelope (no sibling folder beside the staged
    package), and the device driver answers NOT_IN_BUILD even at T2."""
    case = CASES["telos"]
    assert (case.class_plan, case.class_expected) == ("A", "A")
    checks = {c.name: c for c in case.checks}
    for check in checks.values():
        if check.kind == "call":
            assert tool_policy("telos", check.tool) is not None, check.name
    assert checks["fresh_main"].tool == "telos.catalog"
    refused = checks["fresh_workflow_t1_refused"]
    assert (refused.tool, refused.tier, refused.expect_status) == ("telos.workflow", "T1", DENIED)
    ran = checks["fresh_workflow_t2_runs"]
    assert (ran.tool, ran.tier, ran.expect_status) == ("telos.workflow", "T2", 200)
    good = {"status": "UNVERIFIABLE", "native": {"reason": "flagship_workflow_unjoinable"}}
    assert ran.assert_(good) is True
    for bad in ({"status": "MATCH", "native": {"reason": "flagship_workflow_unjoinable"}},
                {"status": "UNVERIFIABLE", "native": {"reason": "other"}}, [], None):
        assert ran.assert_(bad) is False, bad
    out = checks["fresh_native_control_not_in_build"]
    assert (out.tool, out.tier, out.expect_status, out.expect_code) == (
        "telos.native.control", "T2", REFUSED, "NOT_IN_BUILD")
    for name, tool in (("fresh_room_t1_refused", "telos.room"),
                       ("fresh_proof_t1_refused", "telos.proof")):
        check = checks[name]
        assert (check.tool, check.tier, check.expect_status) == (tool, "T1", DENIED)


def test_the_telos_checks_run_a_proof_and_send_a_stray_argument():
    """The card says catalog and proofs: an installed call runs the build proof
    and needs the verifier's own MATCH. A catalog call with arguments must
    still answer the catalog, since the engine passes telos none."""
    checks = {c.name: c for c in CASES["telos"].checks}
    proof = checks["fresh_proof_build"]
    assert (proof.tool, proof.tier, proof.expect_status) == ("telos.proof.build", "T1", 200)
    good = {"schema": "project-telos.build-proof-packet/v1",
            "verifier": {"verdict": "MATCH", "failures": []}}
    assert proof.assert_(good) is True
    for bad in ({**good, "verifier": {"verdict": "DRIFT", "failures": []}},
                {**good, "verifier": {"verdict": "MATCH", "failures": ["check.drift"]}},
                {**good, "schema": "project-telos.proof-packet/v1"},
                {"schema": good["schema"]}, [], None):
        assert proof.assert_(bad) is False, bad
    stray = checks["fresh_catalog_drops_arguments"]
    assert (stray.tool, stray.tier, stray.expect_status) == ("telos.catalog", "T1", 200)
    ((tool, args),) = stray.calls(None)
    assert tool == "telos.catalog" and args
    assert stray.assert_({"schema": "project-telos.mcp-tool-catalog/v1",
                          "tools": [{"name": "telos.status"}]}) is True
    assert stray.assert_({"schema": "project-telos.mcp-tool-catalog/v1", "tools": []}) is False

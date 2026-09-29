"""The lane smoke measures the build, not the smoke harness or the host.

Correctness C3, C5, C6 and POLICY-DECISION C-16:

- a payload lane's plan carries the gateway's own confinement (lane folder,
  state defaults, scoped temp), so canon finds its blocks folder;
- a fixture that needs a model server runs only when one answers, and the
  receipt says which, so the verdict does not depend on the build machine;
- the relay fixture asks for every widening argument and routes them through
  the engine's guard, so the assertion can fail if the guard stops forcing;
- a lane that writes under the home outside its folder fails the smoke.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from harness.lane_tier_gate import guard_args
from harness.mcp_client import LaunchSpec
from scripts import frozen_gateway_lane_smoke as smoke
from scripts.lane_smoke_containment import outside_writes, snapshot
from scripts.lane_smoke_fixtures import FIXTURES, model_server_answering
from tests.test_frozen_gateway_lane_smoke import FAKE_SERVER, PLEXUS_REPLIES, _fake, _rows

_WRITER = FAKE_SERVER.replace(
    "replies = json.loads(sys.argv[1])",
    "replies = json.loads(sys.argv[1])\n"
    "import os, pathlib\n"
    "pathlib.Path(sys.argv[2]).write_text('x')")


def test_a_payload_plan_carries_the_gateway_confinement(tmp_path, monkeypatch):
    from harness import bundled_lane_admission as admission

    def admit(name, **_kw):
        launch = LaunchSpec(("engine.exe", "--bundled-lane-mcp", name), inherit_env=False,
                            env_overrides=(("PATH", "C:/Windows/System32"),))
        return admission.BundledLaneAdmission(launch, {}, ())

    from harness import bundled_lane_descriptor as descriptor
    monkeypatch.setattr(admission, "admit_bundled_lane", admit)
    monkeypatch.setattr(descriptor, "resolve_expected",
                        lambda lane, manifest_rows=None: {"health_tool": f"{lane}.status"})
    monkeypatch.setattr(smoke, "_manifest_rows", lambda _exe, _repo: {"canon": {}})
    home = tmp_path / "home"
    plans = smoke.bundled_lane_plans(tmp_path / "engine.exe", home)
    env = dict(plans["canon"].launch.env_overrides)
    folder = home.resolve() / "lanes" / "canon"
    assert Path(plans["canon"].launch.cwd) == folder
    assert env["CANON_BLOCKS_DIR"] == str(folder / "blocks")
    assert Path(env["TEMP"]).is_relative_to(folder)


_RELAY_OK = {"final_answer": "ok", "request_binding": {
    "allow_write": False, "allow_exec": False, "granted_allow_write": False,
    "granted_allow_exec": False, "requested_root": None, "online": False,
    "check_present": False, "test_cmd_present": False}}
_RELAY_BAD = {**_RELAY_OK, "request_binding": {**_RELAY_OK["request_binding"],
                                                "check_present": True}}


def _relay_plan(reply) -> smoke.LanePlan:
    fake = _fake({"relay.status": {"ok": True}, "local_agent_run": reply},
                 ("relay.status", "local_agent_run"))
    return smoke.LanePlan(fake.launch, "relay.status")


def _relay_run(tmp_path, reply, model_server):
    rows = {"relay": {"expected": "health", "bar": "B"}}
    return smoke.run_lane_smoke({"relay": _relay_plan(reply)}, rows, home=tmp_path,
                                timeout=20, model_server=model_server)


def test_a_model_backed_main_step_is_measured_but_never_host_gated(tmp_path):
    """C5: whether and how fast a host model answers never changes the verdict;
    the receipt records it. The row stays at health on every host."""
    without = _relay_run(tmp_path, _RELAY_OK, False)
    assert without["model_server_answering"] is False
    assert without["lanes"]["relay"]["reason"] == "no_model_server"
    assert without["verdict"] == "BELOW_BAR_EXPECTED"
    served = _relay_run(tmp_path, _RELAY_OK, True)
    assert served["lanes"]["relay"]["level"] == "health"
    assert served["lanes"]["relay"]["reason"] == "model_main_ok"
    assert served["verdict"] == "BELOW_BAR_EXPECTED"


def test_a_model_backed_reply_that_shows_a_widened_run_fails(tmp_path):
    """C6: a reply that came back with a check (or write, exec, online) is a
    guard regression, and fails the smoke whatever the host."""
    served = _relay_run(tmp_path, _RELAY_BAD, True)
    assert served["lanes"]["relay"]["reason"] == "main_assertion_failed_model"
    assert served["verdict"] == "FAIL" and served["failures"] == ["relay"]


def test_nothing_listening_is_no_model_server():
    assert model_server_answering((("127.0.0.1", 9),), timeout=0.2) is False


def test_the_relay_fixture_asks_for_everything_and_the_guard_takes_it_away(tmp_path):
    fixture = FIXTURES["relay"]
    assert fixture.needs_model_server
    [(tool, args)] = fixture.calls(tmp_path, tmp_path / "work")
    assert args["allow_exec"] is True and args["check"] and args["online"] is True
    sent = guard_args("relay", tool, args)
    assert sent == {"goal": args["goal"], "max_steps": 1, "allow_write": False,
                    "allow_exec": False, "online": False}
    bound = {"allow_write": False, "allow_exec": False, "granted_allow_write": False,
             "granted_allow_exec": False, "requested_root": None, "online": False,
             "check_present": False, "test_cmd_present": False}
    assert fixture.check({"final_answer": "ok", "request_binding": bound})
    for key, value in (("allow_exec", True), ("check_present", True), ("online", True),
                       ("requested_root", str(tmp_path))):
        assert not fixture.check({"final_answer": "ok",
                                  "request_binding": {**bound, key: value}}), key


def test_a_lane_that_writes_outside_its_folder_fails(tmp_path):
    stray = tmp_path / "stray.txt"
    launch = LaunchSpec((sys.executable, "-c", _WRITER, json.dumps(PLEXUS_REPLIES),
                         str(stray)), allowed_tools=("plexus.status", "plexus_route"))
    plan = smoke.LanePlan(launch, "plexus.status")
    receipt = smoke.run_lane_smoke({"plexus": plan}, _rows(plexus="main"), home=tmp_path,
                                   timeout=20, model_server=False)
    assert receipt["lanes"]["plexus"]["outside_writes"] == ["stray.txt"]
    assert receipt["verdict"] == "FAIL" and receipt["failures"] == ["plexus"]


def test_writes_inside_the_lane_and_fixture_folders_are_allowed(tmp_path):
    before = snapshot(tmp_path)
    for rel in ("lanes/gather/db.json", "fixtures/gather/in.md", "lanes/other/x"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("x", encoding="utf-8")
    assert outside_writes(before, snapshot(tmp_path), "gather") == ["lanes/other/x"]


def test_a_quiet_lane_passes_containment(tmp_path):
    plan = _fake(PLEXUS_REPLIES, ("plexus.status", "plexus_route"))
    receipt = smoke.run_lane_smoke({"plexus": plan}, _rows(plexus="main"), home=tmp_path,
                                   timeout=20, model_server=False)
    assert receipt["lanes"]["plexus"]["outside_writes"] == []
    assert receipt["verdict"] == "PASS"

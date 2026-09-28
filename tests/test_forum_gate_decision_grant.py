"""forum 1.15's gate decision grant belongs to the engine's T2 approval.

forum 1.15 lists and runs gate_approve, gate_edit and gate_reject only on a
launch that carries --allow-gate-decisions, so a model connected to an ordinary
launch cannot decide its own gate. The engine starts forum without the flag and
adds it only to the launch of one call the owner approved at T2 for one of the
three tools (lane_tier_gate.widen_for_call). That holds in every install mode:
a pip or source launch gets the flag at the end of its argv, and the frozen
child mode passes it to forum's serve_stdio as allow_gate_decisions=True. A T1
call, another tool, an alias name, the GET proxy and a plugin plan never get it.

The last test starts the real forum 1.15.1 from its tag's source, where a
checkout is present (FLYWHEEL_LANE_CHECKOUT_ROOT, default C:/dev).
"""
from __future__ import annotations

import io
import os
import subprocess
import sys
import tarfile
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from harness import lane_tool_policy as policy
from harness import lanes, plugins  # bound before any test patches resolve_mcp_launch
from harness.lane_tier_gate import widen_for_call
from harness.lane_tool_policy_args import LAUNCH_GRANTS
from harness.mcp_client import LaunchSpec

GRANT = "--allow-gate-decisions"
DECISIONS = ("gate_approve", "gate_edit", "gate_reject")
FROZEN = LaunchSpec(("flywheel-gateway.exe", "--bundled-lane-mcp", "forum"),
                    inherit_env=False, allowed_tools=tuple(policy.admitted_tools("forum")))
PIP = LaunchSpec(("python.exe", "-m", "forum.cli", "mcp"))
FORUM_PIN = "86e1b12e20de1938d059eb6b264e20ea2a742c98"
CHECKOUT_ROOT = Path(os.environ.get("FLYWHEEL_LANE_CHECKOUT_ROOT", "C:/dev"))


def test_only_forums_three_decision_tools_name_a_launch_grant():
    named = {(lane, tool): entry.launch_grant
             for lane, tools in policy.LANE_TOOL_POLICY.items()
             for tool, entry in tools.items() if entry.launch_grant}
    assert named == {("forum", tool): GRANT for tool in DECISIONS}
    assert LAUNCH_GRANTS == {"forum": {GRANT: "allow_gate_decisions"}}
    for tool in DECISIONS:
        entry = policy.tool_policy("forum", tool)
        assert (entry.tier, entry.effect, entry.not_in_build) == ("T2", "approve", "")
        assert tool not in policy.admitted_tools("forum")


def test_the_policy_check_refuses_a_misplaced_launch_grant():
    """Control: a grant on a T1 tool would ride every ordinary call, and a flag
    the lane does not take is a typo the engine would pass on."""
    table = {"forum": {"route": policy.ToolPolicy(reason="r", launch_grant=GRANT),
                       "gate_edit": policy.ToolPolicy(tier="T2", effect="approve", reason="r",
                                                      launch_grant="--allow-everything")},
             "gather": {"gather.docs": policy.ToolPolicy(reason="r", tier="T2",
                                                         launch_grant=GRANT)}}
    problems = policy.validate_policy(table)
    assert any("forum route: a launch grant needs a T2 tool" in p for p in problems)
    assert any("forum gate_edit: launch grant '--allow-everything'" in p for p in problems)
    assert any("gather.docs: launch grant '--allow-gate-decisions'" in p for p in problems)
    assert policy.validate_policy() == []


@pytest.mark.parametrize("tool", DECISIONS)
def test_a_granted_decision_call_carries_the_grant_on_its_own_launch(tool):
    frozen = widen_for_call(FROZEN, "forum", tool, "T2")
    assert frozen.argv == (*FROZEN.argv, GRANT)
    assert frozen.allowed_tools == (*FROZEN.allowed_tools, tool)
    assert widen_for_call(PIP, "forum", tool, "T3").argv == (*PIP.argv, GRANT)
    assert FROZEN.argv[-1] == "forum" and PIP.argv[-1] == "mcp"      # inputs untouched


def test_no_other_call_gets_the_grant():
    assert widen_for_call(FROZEN, "forum", "gate_approve", "T1") == FROZEN
    assert widen_for_call(PIP, "forum", "gate_approve", "") == PIP
    assert widen_for_call(FROZEN, "forum", "gate_list", "T2") == FROZEN
    submit = widen_for_call(FROZEN, "forum", "forum.submit", "T2")
    assert submit.argv == FROZEN.argv and "forum.submit" in submit.allowed_tools
    # an alias forum resolves to gate_approve is not in the table: no grant
    assert widen_for_call(PIP, "forum", "forum.gate.approve", "T2") == PIP
    assert widen_for_call(FROZEN, "relay", "gate_approve", "T2") == FROZEN
    granted = replace(PIP, argv=(*PIP.argv, GRANT))
    assert widen_for_call(granted, "forum", "gate_edit", "T2").argv.count(GRANT) == 1


def _record_launches(monkeypatch, base: LaunchSpec) -> list:
    import harness.mcp_client as mcp_client
    spawned: list = []

    class _Client:
        def __init__(self, command, **_kw):
            spawned.append(command)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return None

        def call_text(self, name, args):
            return {"ok": True, "text": '{"ok": true}', "raw": {}}

    monkeypatch.setattr(lanes, "resolve_mcp_launch", lambda name, *a, **k: base)
    monkeypatch.setattr(mcp_client, "MCPClient", _Client)
    return spawned


@pytest.mark.parametrize("base", [FROZEN, PIP], ids=["frozen", "pip"])
def test_the_lane_call_route_grants_only_an_approved_decision(monkeypatch, base):
    from harness.lane_caller import call_lane_tool
    spawned = _record_launches(monkeypatch, base)
    args = {"run_seq": 1, "wave": 0, "approver": "owner"}
    assert call_lane_tool("forum", "gate_approve", dict(args), governance_tier="T2") == \
        {"ok": True}
    assert spawned[-1].argv == (*base.argv, GRANT)
    denied = call_lane_tool("forum", "gate_approve", dict(args), governance_tier="T1")
    assert denied.get("governance_denied") is True and len(spawned) == 1
    call_lane_tool("forum", "gate_list", {}, governance_tier="T2")
    call_lane_tool("forum", "plan", {"request": "a plan"})
    assert [launch.argv for launch in spawned[1:]] == [base.argv, base.argv]


def test_the_proxy_and_plugin_launches_never_carry_the_grant(monkeypatch):
    from harness.gateway_lane_calls import _proxy_launch, _proxy_refusal
    monkeypatch.setattr(lanes, "resolve_mcp_launch", lambda name, *a, **k: PIP)
    monkeypatch.setattr(plugins, "resolve_mcp_launch", lambda name, *a, **k: PIP)
    assert GRANT not in _proxy_launch("forum").argv
    assert _proxy_refusal("forum", "gate_approve", {})["code"] == "CAPABILITY_NOT_ADMITTED"
    launch, kind, _slots, _refs = plugins.plugin_execution_plan("forum")
    assert kind == "lane" and GRANT not in launch.argv


def _dispatch(monkeypatch, argv):
    from harness import bundled_lane_admission, bundled_lane_descriptor
    monkeypatch.setattr(bundled_lane_descriptor, "module_importable", lambda _name: True)
    served, imported = [], []

    async def serve_stdio(**kwargs):
        served.append(kwargs)
        return 0

    def fake_import(name):
        imported.append(name)
        return SimpleNamespace(serve_stdio=serve_stdio)

    code = bundled_lane_admission.dispatch_bundled_lane_mcp(
        argv, import_module_fn=fake_import, executable="flywheel-gateway.exe", environ={})
    return code, served, imported


def test_the_frozen_child_mode_passes_the_grant_to_serve_stdio(monkeypatch):
    code, served, imported = _dispatch(monkeypatch, ["--bundled-lane-mcp", "forum", GRANT])
    assert (code, served, imported) == (0, [{"allow_gate_decisions": True}],
                                        ["forum.mcp_surface"])
    code, served, _imported = _dispatch(monkeypatch, ["--bundled-lane-mcp", "forum"])
    assert (code, served) == (0, [{}])


@pytest.mark.parametrize("argv", [
    ["--bundled-lane-mcp", "forum", GRANT, GRANT],
    ["--bundled-lane-mcp", "forum", "--allow-exec"],
    ["--bundled-lane-mcp", "relay", GRANT],
    ["--bundled-lane-mcp", "forum", "extra"],
])
def test_the_frozen_child_mode_refuses_any_other_token(monkeypatch, argv):
    code, served, imported = _dispatch(monkeypatch, argv)
    assert (code, served, imported) == (2, [], [])


def _forum_source(tmp_path: Path) -> Path:
    checkout = CHECKOUT_ROOT / "public" / "forum"
    if not (checkout / ".git").exists():
        pytest.skip(f"no forum checkout under {CHECKOUT_ROOT}")
    probe = subprocess.run(
        ["git", "-C", str(checkout), "cat-file", "-e", f"{FORUM_PIN}^{{commit}}"],
        capture_output=True, check=False)
    if probe.returncode != 0:
        pytest.skip("the forum checkout lacks the pinned commit")
    data = subprocess.run(["git", "-C", str(checkout), "archive", FORUM_PIN, "src"],
                          capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        tar.extractall(tmp_path / "forum", filter="data")
    return tmp_path / "forum" / "src"


@pytest.mark.timeout(180)
def test_forum_1_15_1_serves_decisions_only_on_the_granted_launch(tmp_path):
    from harness.lane_caller import lane_refusal
    from harness.mcp_client import MCPClient
    src = _forum_source(tmp_path)
    work = tmp_path / "lane"
    work.mkdir()
    env = {**{k: v for k, v in os.environ.items() if k.upper() in ("PATH", "SYSTEMROOT")},
           "PYTHONPATH": str(src), "PYTHONUTF8": "1"}
    launch = LaunchSpec((sys.executable, "-m", "forum.cli", "mcp"), cwd=str(work),
                        env_overrides=tuple(env.items()), inherit_env=False)
    args = {"run_seq": 1, "wave": 0, "approver": "owner"}
    with MCPClient(launch, timeout=60) as client:
        names = {tool["name"] for tool in client.list_all_tools()}
        refused = client.call_text("gate_approve", args)
    assert "gate_list" in names and not names & set(DECISIONS)
    assert lane_refusal("forum", "gate_approve", refused["raw"])["reason"] == \
        "lane_grant_required"
    with MCPClient(widen_for_call(launch, "forum", "gate_approve", "T2"), timeout=60) as client:
        names = {tool["name"] for tool in client.list_all_tools()}
        decided = client.call_text("gate_approve", args)
    assert set(DECISIONS) <= names
    assert decided["raw"]["structuredContent"]["code"] == "NOT_FOUND"   # no gate pending


def test_the_docs_count_the_tools_an_ordinary_forum_launch_lists():
    """An ordinary launch lists the row's tools minus the ones that need a launch
    grant; the forum page, the policy review and the notes carry that count."""
    import json
    root = Path(__file__).resolve().parents[1]
    row = next(json.loads(line) for line in (root / "packaging" / "python-lane-payloads.jsonl")
               .read_text(encoding="utf-8").splitlines()
               if line.strip() and json.loads(line)["lane"] == "forum")
    served = row["mcp"]["static_tool_names"]
    granted = [t for t in served if (policy.tool_policy("forum", t) or
                                     SimpleNamespace(launch_grant="")).launch_grant]
    assert sorted(granted) == sorted(DECISIONS)
    ordinary = len(served) - len(granted)
    for parts in (("docs", "features", "forum.md"), ("project-docs", "lanes", "POLICY-REVIEW.md")):
        text = " ".join(root.joinpath(*parts).read_text(encoding="utf-8").split())
        assert f"lists the {ordinary} tools of an ordinary launch" in text, parts
    notes = " ".join((root / "RELEASE-NOTES-1.1.0.md")
                     .read_text(encoding="utf-8").split())
    assert len(granted) == 3 and "which leaves the three out" in notes
    assert "The app has no control for them in this release" in notes

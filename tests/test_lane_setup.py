"""Setup items come from real checks, and the key item never reads a value.

The key item reports three facts per granted name: granted, present, and
validated only after a bound call succeeded (H-7). Presence comes from where
a value would be resolved (environment or keychain), as a word, never the
value. The test plants a fake key value in the environment and in the fake
keychain and checks it appears nowhere in the answer.
"""
from __future__ import annotations

import json

from harness.lane_setup import (GIT_MISSING, NODE_MISSING, SetupChecks, lane_needs,
                                lane_setup)
from harness.tool_discovery import ToolFinding

FAKE_KEY = "sk-planted-fake-value-0123456789"


def _finding(tool, ok, **kw):
    return ToolFinding(tool, ok, kw.get("path"), kw.get("version"),
                       kw.get("source", "not_found"), "", "fake")


def _checks(tmp_path, **seams):
    env = {"FLYWHEEL_HOME": str(tmp_path / "home"), "FORUM_KEY": FAKE_KEY}
    base = dict(node=lambda: _finding("node", False), git=lambda: _finding("git", False),
                model_health=lambda: {"any_live": False, "tiers": []},
                key_source=lambda _n: "absent", key_grants=lambda _l: (),
                validated_keys=lambda _l: set())
    base.update(seams)
    return SetupChecks(env, **base)


def _item(result, item_id):
    return next(i for i in result["items"] if i["id"] == item_id)


def test_key_item_reports_granted_present_not_validated_and_never_a_value(tmp_path):
    reads = []

    def source(name):
        reads.append(name)
        return {"FORUM_KEY": "env", "OTHER_KEY": "absent"}[name]

    checks = _checks(tmp_path, key_source=source,
                     key_grants=lambda lane: ("FORUM_KEY", "OTHER_KEY") if lane == "forum" else (),
                     validated_keys=lambda _l: set())
    result = lane_setup("forum", checks)
    item = _item(result, "provider_key")
    assert item["met"] is True
    assert item["facts"]["keys"] == [
        {"name": "FORUM_KEY", "granted": True, "present": True, "validated": False},
        {"name": "OTHER_KEY", "granted": True, "present": False, "validated": False}]
    assert "FORUM_KEY: granted, present, not validated" in item["copy"]
    assert reads == ["FORUM_KEY", "OTHER_KEY"]
    assert FAKE_KEY not in json.dumps(result)


def test_key_item_reads_validated_only_from_a_recorded_success(tmp_path):
    checks = _checks(tmp_path, key_source=lambda _n: "keychain",
                     key_grants=lambda _l: ("FORUM_KEY",),
                     validated_keys=lambda _l: {"FORUM_KEY"})
    item = _item(lane_setup("forum", checks), "provider_key")
    assert item["facts"]["keys"][0]["validated"] is True
    assert "granted, present, validated" in item["copy"]


def test_key_item_without_a_grant_states_the_real_steps(tmp_path):
    item = _item(lane_setup("forum", _checks(tmp_path)), "provider_key")
    assert item["met"] is False
    assert "Keys panel on the Endpoints screen" in item["copy"]
    assert "env_allow" in item["copy"] and "lanes.json" in item["copy"]


def test_key_item_goes_through_presence_only(tmp_path, monkeypatch):
    """The default seam is keychain.credential_source; resolve_credential, the
    one function that returns a value, is never called."""
    import harness.keychain as keychain
    monkeypatch.setattr(keychain, "resolve_credential",
                        lambda _n: (_ for _ in ()).throw(AssertionError("read a value")))
    monkeypatch.setattr(keychain, "keychain_get", lambda _n: FAKE_KEY)
    checks = SetupChecks({"FLYWHEEL_HOME": str(tmp_path)},
                         key_grants=lambda _l: ("FORUM_KEY",),
                         validated_keys=lambda _l: set())
    result = lane_setup("forum", checks)
    assert _item(result, "provider_key")["facts"]["keys"][0]["present"] is True
    assert FAKE_KEY not in json.dumps(result)


def test_model_item_comes_from_local_agent_health(tmp_path):
    down = _checks(tmp_path, model_health=lambda: {"any_live": False, "tiers": [
        {"backend": "serve", "healthy": False, "detail": "x"},
        {"backend": "ollama", "healthy": False, "detail": "y"}]})
    item = _item(lane_setup("relay", down), "model_server")
    assert item["met"] is False
    assert item["copy"] == ("Start a model server: Ollama with a pulled model at "
                            "127.0.0.1:11434, or a server at 127.0.0.1:8765.")
    up = _checks(tmp_path, model_health=lambda: {"any_live": True, "tiers": [
        {"backend": "ollama", "healthy": True, "detail": "qwen"}]})
    item = _item(lane_setup("relay", up), "model_server")
    assert item["met"] is True and "ollama" in item["copy"]
    assert item["facts"]["tiers"] == [{"backend": "ollama", "healthy": True}]


def test_node_and_git_come_from_tool_discovery(tmp_path):
    missing = _checks(tmp_path)
    assert _item(lane_setup("learn", missing), "node")["copy"] == NODE_MISSING
    assert _item(lane_setup("index", missing), "git")["copy"] == GIT_MISSING
    found = _checks(tmp_path,
                    node=lambda: _finding("node", True, path="C:/n/node.exe",
                                          version="v22.1.0", source="bundled"),
                    git=lambda: _finding("git", True, path="C:/g/git.exe", source="user_path"))
    node = _item(lane_setup("learn", found), "node")
    assert node["met"] and node["copy"] == "Node v22.1.0 at C:/n/node.exe."
    assert node["facts"]["source"] == "bundled"
    assert _item(lane_setup("index", found), "git")["met"] is True


def test_node_none_override_reads_not_found_through_the_real_discovery(tmp_path):
    checks = SetupChecks({"FLYWHEEL_HOME": str(tmp_path), "FLYWHEEL_NODE": "none"})
    item = _item(lane_setup("learn", checks), "node")
    assert item["met"] is False and item["facts"]["source"] == "disabled"


def test_canon_blocks_folder_and_count(tmp_path):
    checks = _checks(tmp_path)
    item = _item(lane_setup("canon", checks), "canon_blocks")
    folder = tmp_path / "home" / "lanes" / "canon" / "blocks"
    assert item["met"] is False and item["copy"] == f"Put blocks in {folder.resolve()}."
    folder.mkdir(parents=True)
    (folder / "one.json").write_text("{}", encoding="utf-8")
    item = _item(lane_setup("canon", _checks(tmp_path)), "canon_blocks")
    assert item["met"] is True and item["facts"]["count"] == 1


def test_project_folder_refuses_the_flywheel_home(tmp_path):
    home = tmp_path / "home"
    root_file = home / "lanes" / "local-model" / "root"
    root_file.parent.mkdir(parents=True)
    root_file.write_text(str(home / "inside"), encoding="utf-8")
    (home / "inside").mkdir()
    item = _item(lane_setup("local-model", _checks(tmp_path)), "project_folder")
    assert item["met"] is False and item["facts"]["code"] == "local_model_root_protected"
    project = tmp_path / "project"
    project.mkdir()
    root_file.write_text(str(project), encoding="utf-8")
    item = _item(lane_setup("local-model", _checks(tmp_path)), "project_folder")
    assert item["met"] is True


def test_needs_leave_out_items_only_not_in_build_tools_use():
    assert "claude_cli" not in lane_needs("articulate")
    assert lane_needs("index") == ["git"]
    assert "provider_key" in lane_needs("forum") and "provider_key" in lane_needs("mneme")
    assert lane_needs("gather") == []


def test_each_item_is_evaluated_once_per_request(tmp_path):
    calls = []
    checks = _checks(tmp_path, node=lambda: calls.append(1) or _finding("node", False))
    lane_setup("learn", checks)
    lane_setup("telos", checks)
    assert len(calls) == 1

"""Falsifiers for the lane layer (harness/lanes.py).

The lane roster must be honest about what is installed vs declared vs missing,
and the install-name -> command asymmetry must map correctly (pip install
gather-engine exposes the `gather` command, etc.). A missing lane never
crashes the roster; it reports `missing`/`declared`.
"""
from pathlib import Path

import harness.lanes as lanes
import harness.mcp_client as mcp_client
from harness.lanes import (
    LANES, MISSING, DECLARED, LIVE, STALE,
    install_lane, lane_status, lane_roster, lane_report, resolve_mcp_command,
)


def test_registry_covers_the_expected_lanes():
    # the six spine flagships + local-model (the engine) + relay (execution) +
    # plexus (wiring) + mneme (memory) + calibrate-pro (its own calibration lane)
    assert set(LANES) == {"gather", "crucible", "index", "forum",
                          "learn", "telos", "local-model", "relay", "plexus", "mneme",
                          "calibrate-pro"}


def test_install_name_to_command_asymmetry_is_mapped():
    # Each pip lane's distribution name differs from its command.
    assert LANES["index"].install_name == "index-graph"
    assert LANES["index"].command == "index"
    assert LANES["gather"].install_name == "gather-engine"
    assert LANES["gather"].command == "gather"
    assert LANES["crucible"].install_name == "crucible-bench"
    assert LANES["crucible"].command == "crucible"
    assert LANES["forum"].install_name == "forum-engine"
    assert LANES["forum"].command == "forum"


def test_every_lane_has_an_mcp_command_and_organ():
    for name, lane in LANES.items():
        cmd = resolve_mcp_command(name)
        assert isinstance(cmd, list) and len(cmd) >= 1
        assert lane.organ, f"{name} has no organ assigned"
        assert lane.role, f"{name} has no role assigned"
        assert lane.kind in ("pip", "npm", "bundled")


def test_unknown_lane_reports_missing_not_crash():
    r = lane_status("nonexistent")
    assert r["status"] == MISSING
    assert "unknown lane" in r["detail"]


def test_roster_includes_every_lane_and_counts_status():
    roster = lane_roster(probe=False)
    assert roster["schema"] == "flywheel.lanes/v1"
    assert roster["n_lanes"] == len(LANES)
    statuses = {r["status"] for r in roster["lanes"]}
    # every reported status is a known value
    assert statuses <= {LIVE, DECLARED, MISSING, STALE}
    assert sum(roster["by_status"].values()) == roster["n_lanes"]


def test_report_is_human_readable_and_nonempty():
    text = lane_report()
    assert "Flywheel lanes" in text
    assert "lanes" in text
    for name in LANES:
        assert name in text


def test_report_names_presence_only_mode():
    roster = lane_roster(probe=False)
    assert "install-presence roster" in lane_report(roster)


def test_bundled_lane_needs_no_install():
    # local-model is the engine lane; it IS Flywheel, so it is never missing.
    r = lane_status("local-model", probe=False)
    assert r["status"] == DECLARED
    assert LANES["local-model"].kind == "bundled"


def test_public_commands_are_portable_declared_argv():
    assert resolve_mcp_command("gather") == ["gather", "mcp"]
    assert resolve_mcp_command("telos") == ["node", "demo/telos-mcp.mjs"]
    assert resolve_mcp_command("local-model") == [
        "python", "-m", "harness.local_mcp"]


def test_install_lane_arg_parser_defaults():
    from harness.cli_entry import _parse_lane_args
    lanes, profile = _parse_lane_args([])
    assert lanes == "all"
    assert profile == "package"


def test_install_lane_arg_parser_explicit():
    from harness.cli_entry import _parse_lane_args
    lanes, profile = _parse_lane_args(["--lanes", "index,gather", "--profile", "source"])
    assert lanes == "index,gather"
    assert profile == "source"


def test_install_lane_bundled_is_noop():
    # The bundled lane (local-model) needs no install; install_lane reports OK.
    from harness.lanes import install_lane
    r = install_lane("local-model")
    assert r["installed"] is True
    assert "bundled" in r["detail"]


def test_registry_roundtrip(tmp_path, monkeypatch):
    # write_registry -> read_registry preserves the data.
    import json
    from harness.lanes import write_registry, read_registry, LANE_REGISTRY_PATH
    monkeypatch.setattr("harness.lanes.LANE_REGISTRY_PATH", tmp_path / "lanes.json")
    write_registry({"index": {"install_name": "index-graph", "installed": True}})
    loaded = read_registry()
    assert loaded["index"]["installed"] is True


def test_source_repo_prefers_explicit_workspace_root(tmp_path, monkeypatch):
    explicit = tmp_path / "explicit" / "public" / "gather"
    inferred = tmp_path / "checkout" / "public" / "gather"
    explicit.mkdir(parents=True)
    inferred.mkdir(parents=True)
    monkeypatch.setenv("FLYWHEEL_WORKSPACE_ROOT", str(tmp_path / "explicit"))
    monkeypatch.setattr(lanes, "REPO", tmp_path / "checkout" / "flywheel")
    assert lanes.resolve_source_repo(LANES["gather"]) == explicit.resolve()


def test_source_repo_uses_inferred_workspace_root(tmp_path, monkeypatch):
    source = tmp_path / "workspace" / "public" / "gather"
    source.mkdir(parents=True)
    monkeypatch.delenv("FLYWHEEL_WORKSPACE_ROOT", raising=False)
    monkeypatch.setattr(lanes, "REPO", tmp_path / "workspace" / "flywheel")
    assert lanes.resolve_source_repo(LANES["gather"]) == source.resolve()


def test_source_repo_uses_matching_container_sibling(tmp_path, monkeypatch):
    source = tmp_path / "workspace" / "public" / "gather"
    source.mkdir(parents=True)
    monkeypatch.delenv("FLYWHEEL_WORKSPACE_ROOT", raising=False)
    monkeypatch.setattr(
        lanes, "REPO", tmp_path / "workspace" / "public" / "flywheel")
    assert lanes.resolve_source_repo(LANES["gather"]) == source.resolve()
    assert "public/public" not in source.as_posix()


def test_source_repo_is_none_when_checkout_is_absent(tmp_path, monkeypatch):
    monkeypatch.delenv("FLYWHEEL_WORKSPACE_ROOT", raising=False)
    monkeypatch.setattr(lanes, "REPO", tmp_path / "workspace" / "flywheel")
    assert lanes.resolve_source_repo(LANES["gather"]) is None


class _ProbeClient:
    tools = [{"name": "gather.status"}]
    response = {"ok": True, "text": "ok"}
    launch = None

    def __init__(self, launch, **kwargs):
        type(self).launch = launch

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def list_tools(self):
        return list(self.tools)

    def call_text(self, name, arguments):
        return dict(self.response)


def test_source_checkout_is_probed_when_package_is_absent(tmp_path, monkeypatch):
    source = tmp_path / "workspace" / "public" / "gather"
    source.mkdir(parents=True)
    monkeypatch.setattr(lanes, "REPO", tmp_path / "workspace" / "flywheel")
    monkeypatch.setattr(lanes, "_installed_version", lambda lane: None)
    monkeypatch.setattr(lanes, "_importable", lambda top: False)
    monkeypatch.setattr(mcp_client, "MCPClient", _ProbeClient)
    result = lane_status("gather", probe=True)
    assert result["status"] == LIVE
    assert _ProbeClient.launch.cwd == str(source.resolve())


def test_presence_only_installed_lane_is_declared_not_live(monkeypatch):
    monkeypatch.setattr(lanes, "_installed_version", lambda lane: "1.2.3")
    assert lane_status("gather", probe=False)["status"] == DECLARED


def test_missing_health_tool_is_stale(monkeypatch):
    monkeypatch.setattr(_ProbeClient, "tools", [{"name": "gather.run"}])
    monkeypatch.setattr(mcp_client, "MCPClient", _ProbeClient)
    result = lanes._probe_lane("gather", "1.2.3", 1.0, present=True)
    assert result["status"] == STALE
    assert "health tool" in result["detail"]


def test_health_tool_error_is_stale(monkeypatch):
    monkeypatch.setattr(_ProbeClient, "tools", [{"name": "gather.status"}])
    monkeypatch.setattr(
        _ProbeClient, "response", {"ok": False, "text": "not healthy"})
    monkeypatch.setattr(mcp_client, "MCPClient", _ProbeClient)
    result = lanes._probe_lane("gather", "1.2.3", 1.0, present=True)
    assert result["status"] == STALE
    assert "not healthy" in result["detail"]


def test_failed_probe_of_present_lane_is_declared(monkeypatch):
    class FailingClient:
        def __init__(self, *args, **kwargs):
            raise OSError("cannot launch")

    monkeypatch.setattr(mcp_client, "MCPClient", FailingClient)
    result = lanes._probe_lane("gather", None, 1.0, present=True)
    assert result["status"] == DECLARED
    assert "cannot launch" in result["detail"]


def test_source_install_without_checkout_does_not_invoke_installer(
        tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(lanes, "REPO", tmp_path / "workspace" / "flywheel")
    monkeypatch.setattr(lanes.subprocess, "run", lambda *a, **k: calls.append(a))
    result = install_lane("gather", profile="source")
    assert result["installed"] is False
    assert "source checkout" in result["detail"]
    assert calls == []


def test_source_install_uses_matching_container_checkout(tmp_path, monkeypatch):
    source = tmp_path / "workspace" / "public" / "gather"
    source.mkdir(parents=True)
    monkeypatch.setattr(
        lanes, "REPO", tmp_path / "workspace" / "public" / "flywheel")
    calls = []

    class Installed:
        returncode = 0
        stdout = "installed"
        stderr = ""

    monkeypatch.setattr(
        lanes.subprocess, "run",
        lambda command, **kwargs: calls.append(command) or Installed())
    result = install_lane("gather", profile="source")
    assert result["installed"] is True
    assert calls == [["pip", "install", "-e", str(source.resolve())]]

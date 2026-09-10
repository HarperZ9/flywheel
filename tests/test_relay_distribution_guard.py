"""A collided package name must never install or launch another project."""
from types import SimpleNamespace

import pytest

from harness import lanes


@pytest.mark.parametrize("name", ["relay", "canon", "mneme", "plexus", "telos", "accountable-surface"])
def test_unadmitted_package_install_never_invokes_installer(monkeypatch, name):
    calls = []
    monkeypatch.setattr(lanes.subprocess, "run", lambda *a, **k: (
        calls.append(a[0]) or SimpleNamespace(returncode=0, stdout="", stderr="")))
    result = lanes.install_lane(name)
    assert calls == []
    assert result["installed"] is False
    assert result["code"] == "package_distribution_disabled"


@pytest.mark.parametrize("name", ["relay", "canon", "mneme", "plexus", "telos", "accountable-surface"])
def test_unadmitted_package_has_no_public_command_or_plugin_launch(monkeypatch, name):
    from harness import plugins
    from harness.gateway_lane_calls import _relay_mcp_call
    from harness.gateway_operation import GatewayOperationError
    from harness.gateway_grant_errors import gateway_error_response
    monkeypatch.setattr(lanes, "read_registry", lambda: {})
    monkeypatch.setattr(lanes, "resolve_source_repo", lambda lane: None)
    monkeypatch.setattr(plugins, "_load_custom", lambda: [])
    assert lanes.resolve_mcp_command(name) == []
    row = next(r for r in plugins.plugin_roster()["plugins"] if r["name"] == name)
    assert row["enabled"] is False and row["command"] == []
    assert row["status"] == "unavailable"
    with pytest.raises(GatewayOperationError, match="LANE_UNAVAILABLE") as failure:
        plugins.plugin_execution_plan(name)
    response, status = gateway_error_response(failure.value)
    assert status == 503 and response["error"]["code"] == "LANE_UNAVAILABLE"
    for operation in (plugins.probe_plugin, lambda lane: plugins.call_plugin(lane, "status")):
        result = operation(name)
        assert result["code"] == "LANE_UNAVAILABLE"
        assert result["status"] == "unavailable"
    if name == "relay":
        assert _relay_mcp_call("status", {})["code"] == "LANE_UNAVAILABLE"


@pytest.mark.parametrize("profile,frozen", [
    ("auto", False), ("package", False), ("package", True),
    ("source", False), ("source", True)])
def test_relay_untrusted_package_never_probed_or_launched(
        monkeypatch, tmp_path, profile, frozen):
    monkeypatch.setattr(lanes, "read_registry", lambda: {
        "relay": {"runtime_profile": profile, "runtime_version": "0.1.0",
                  "runtime_python": str(tmp_path / "python.exe")}})
    monkeypatch.setattr(lanes, "resolve_source_repo", lambda lane: None)
    monkeypatch.setattr(lanes, "_frozen", lambda: frozen)
    metadata_calls = []
    monkeypatch.setattr(lanes, "_installed_version", lambda *args: (
        metadata_calls.append(args) or "0.1.0"))
    monkeypatch.setattr(lanes, "_package_runtime_version", lambda *args: (
        metadata_calls.append(args) or "0.1.0"))
    monkeypatch.setattr(lanes, "_importable", lambda name: True)
    launches = []
    class FakeClient:
        def __init__(self, *args, **kwargs):
            launches.append(args)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def list_tools(self):
            return []

    monkeypatch.setattr("harness.mcp_client.MCPClient", FakeClient)
    status = lanes.lane_status("relay", probe=True)
    assert metadata_calls == []
    assert launches == []
    assert status["status"] == "missing"
    assert status["installed_version"] is None
    assert status["package_installable"] is False
    assert "source checkout" in status["detail"]
    with pytest.raises(lanes.LaneRuntimeError):
        lanes.resolve_mcp_launch("relay")


def test_relay_source_still_resolves_and_installs(monkeypatch, tmp_path):
    source = tmp_path / "relay"
    (source / "src" / "relay").mkdir(parents=True)
    (source / "pyproject.toml").write_text('[project]\nversion="0.2.0"\n')
    monkeypatch.setattr(lanes, "read_registry", lambda: {})
    monkeypatch.setattr(lanes, "resolve_source_repo", lambda lane: source)
    monkeypatch.setattr(lanes, "_frozen", lambda: False)
    launch = lanes.resolve_mcp_launch("relay")
    assert launch.cwd == str(source.resolve())
    assert "relay.local_agent_cli" in launch.argv
    calls = []
    monkeypatch.setattr(lanes.subprocess, "run", lambda *a, **k: (
        calls.append(a[0]) or SimpleNamespace(returncode=0, stdout="", stderr="")))
    assert lanes.install_lane("relay", profile="source")["installed"] is True
    assert calls == [["pip", "install", "-e", str(source)]]


def test_other_package_install_keeps_its_distribution(monkeypatch):
    calls = []
    monkeypatch.setattr(lanes.subprocess, "run", lambda *a, **k: (
        calls.append(a[0]) or SimpleNamespace(returncode=0, stdout="", stderr="")))
    assert lanes.install_lane("index")["installed"] is True
    assert calls == [["pip", "install", "index-graph"]]


@pytest.mark.parametrize("profile,frozen", [
    ("package", False), ("package", True), ("source", True)])
def test_source_presence_cannot_bypass_disabled_package_choice(
        monkeypatch, tmp_path, profile, frozen):
    monkeypatch.setattr(lanes, "read_registry", lambda: {"relay": {"runtime_profile": profile}})
    monkeypatch.setattr(lanes, "resolve_source_repo", lambda lane: tmp_path)
    monkeypatch.setattr(lanes, "_frozen", lambda: frozen)
    runtime = lanes.resolve_lane_runtime("relay")
    assert runtime.launch is None
    with pytest.raises(lanes.LaneRuntimeError, match="package_distribution_disabled"):
        runtime.require_launch()


@pytest.mark.parametrize("name", ["relay", "canon", "mneme", "plexus", "telos", "accountable-surface"])
def test_source_plugin_plan_remains_usable_without_public_package_hint(monkeypatch, tmp_path, name):
    from harness import plugins
    monkeypatch.setattr(lanes, "read_registry", lambda: {})
    monkeypatch.setattr(lanes, "resolve_source_repo", lambda lane: tmp_path)
    monkeypatch.setattr(lanes, "_frozen", lambda: False)
    monkeypatch.setattr(plugins, "_load_custom", lambda: [])
    row = next(r for r in plugins.plugin_roster()["plugins"] if r["name"] == name)
    assert row["enabled"] is True and row["command"] == []
    assert row["status"] == "source_selected"
    launch, kind, slots, refs = plugins.plugin_execution_plan(name)
    assert kind == "lane" and slots == refs == ()
    assert launch is not None and launch.argv

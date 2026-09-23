"""The installer must never reach for a distribution name we do not own.

This file was written when relay, mneme and canon had no admitted distribution:
their obvious PyPI names belonged to unrelated projects, so every lane here was
marked package_disabled and the guard asserted that pip install was never
invoked for any of them.

Those three are published now under owned names, so the old assertion would
forbid installing our own package. The property it protected has not changed: a
lane must install the distribution we publish, and must never install the
squatted name. That is asserted directly here rather than by refusing to install
at all, which is the stronger check. Refusing to install proved only that
nothing happened; naming the distribution proves the right thing happens.

Disabled-lane behavior is still covered. It runs against a synthetic lane
injected into the registry, so it cannot quietly stop running once the last real
disabled lane is published. A parametrize over a list that has become empty
reports success, not a gap.
"""
from types import SimpleNamespace

import pytest

from harness import lanes
from harness.lanes_registry import LANES, Lane

# Names on PyPI that belong to someone else. Installing one would fetch a
# stranger's code under our lane's name, which is the failure this file exists
# to prevent.
SQUATTED = {
    "relay-agent",     # an unrelated autonomous issue-labeling project
    "mneme-memory",
    "canon",
}

# Lanes that reclaimed a squatted name by publishing under a prefix. The command
# stays short, so the asymmetry is wider here than a suffix change.
RECLAIMED = {
    "relay": "flywheel-relay",
    "mneme": "flywheel-mneme",
    "canon": "flywheel-canon",
}

PROBE = "zz-probe-disabled-lane"

DISABLED = sorted(name for name, lane in LANES.items() if lane.package_disabled_reason)


@pytest.fixture(autouse=True)
def probe_lane(monkeypatch):
    """A disabled lane that exists for the length of a test.

    Without it the parametrized cases below would cover whatever happens to be
    disabled today, and would cover nothing at all once every lane is published.
    """
    monkeypatch.setitem(lanes.LANES, PROBE, Lane(
        PROBE, "zz-probe-dist", "zz-probe", ("mcp",), "pip", "1.0.0",
        "synthetic lane used only by the distribution guard", "probe",
        source_repo="public/zz-probe", py_module="zz_probe.cli",
        package_disabled_reason=(
            "Synthetic lane, disabled so this guard always has a subject.")))
    return PROBE


def test_no_lane_installs_a_squatted_distribution_name():
    for name, lane in LANES.items():
        assert lane.install_name not in SQUATTED, (
            f"lane {name} would run pip install {lane.install_name}, and that "
            "name belongs to another project")


@pytest.mark.parametrize("name,distribution", sorted(RECLAIMED.items()))
def test_reclaimed_lane_installs_the_distribution_we_publish(
        monkeypatch, name, distribution):
    calls = []
    monkeypatch.setattr(lanes.subprocess, "run", lambda *a, **k: (
        calls.append(a[0]) or SimpleNamespace(returncode=0, stdout="", stderr="")))
    result = lanes.install_lane(name)
    assert result["installed"] is True
    assert calls == [["pip", "install", distribution]]
    assert LANES[name].command == name  # the short command survived the rename


@pytest.mark.parametrize("name", DISABLED + [PROBE])
def test_disabled_package_install_never_invokes_installer(monkeypatch, name):
    calls = []
    monkeypatch.setattr(lanes.subprocess, "run", lambda *a, **k: (
        calls.append(a[0]) or SimpleNamespace(returncode=0, stdout="", stderr="")))
    result = lanes.install_lane(name)
    assert calls == []
    assert result["installed"] is False
    assert result["code"] == "package_distribution_disabled"


@pytest.mark.parametrize("name", DISABLED + [PROBE])
def test_disabled_package_has_no_public_command_or_plugin_launch(monkeypatch, name):
    from harness import plugins
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


@pytest.mark.parametrize("profile,frozen", [
    ("auto", False), ("package", False), ("package", True),
    ("source", False), ("source", True)])
def test_disabled_package_never_probed_or_launched(
        monkeypatch, tmp_path, profile, frozen):
    monkeypatch.setattr(lanes, "read_registry", lambda: {
        PROBE: {"runtime_profile": profile, "runtime_version": "1.0.0",
                "runtime_python": str(tmp_path / "python.exe")}})
    monkeypatch.setattr(lanes, "resolve_source_repo", lambda lane: None)
    monkeypatch.setattr(lanes, "_frozen", lambda: frozen)
    metadata_calls = []
    monkeypatch.setattr(lanes, "_installed_version", lambda *args: (
        metadata_calls.append(args) or "1.0.0"))
    monkeypatch.setattr(lanes, "_package_runtime_version", lambda *args: (
        metadata_calls.append(args) or "1.0.0"))
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
    status = lanes.lane_status(PROBE, probe=True)
    # A disabled lane is never asked what it has installed. resolve_lane_runtime
    # skips that observation while package_disabled_reason is set, which is also
    # why a stale reason hides a working install instead of reporting drift.
    assert metadata_calls == []
    assert launches == []
    assert status["status"] == "missing"
    assert status["installed_version"] is None
    assert status["package_installable"] is False
    # The operator is told why, verbatim, rather than being left with a bare
    # "missing". Asserting the reason is carried through beats matching wording
    # that only the lanes disabled at the time happened to share.
    assert lanes.LANES[PROBE].package_disabled_reason in status["detail"]
    with pytest.raises(lanes.LaneRuntimeError):
        lanes.resolve_mcp_launch(PROBE)


def test_relay_source_still_resolves_and_installs(monkeypatch, tmp_path):
    source = tmp_path / "relay"
    (source / "src" / "relay").mkdir(parents=True)
    (source / "pyproject.toml").write_text('[project]\nversion="0.2.5"\n')
    monkeypatch.setattr(lanes, "read_registry", lambda: {})
    monkeypatch.setattr(lanes, "resolve_source_repo", lambda lane: source)
    monkeypatch.setattr(lanes, "_frozen", lambda: False)
    launch = lanes.resolve_mcp_launch("relay")
    assert launch.cwd == str(source.resolve())
    assert "relay.local_mcp" in launch.argv
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
    monkeypatch.setattr(lanes, "read_registry",
                        lambda: {PROBE: {"runtime_profile": profile}})
    monkeypatch.setattr(lanes, "resolve_source_repo", lambda lane: tmp_path)
    monkeypatch.setattr(lanes, "_frozen", lambda: frozen)
    runtime = lanes.resolve_lane_runtime(PROBE)
    assert runtime.launch is None
    with pytest.raises(lanes.LaneRuntimeError, match="package_distribution_disabled"):
        runtime.require_launch()


@pytest.mark.parametrize("name", DISABLED + [PROBE])
def test_source_plugin_plan_remains_usable_without_public_package_hint(
        monkeypatch, tmp_path, name):
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

import sys

import pytest

from harness.gateway_operation import GatewayOperationError


def _package_launch():
    from harness.mcp_client import LaunchSpec

    return LaunchSpec((sys.executable, "-I", "-m", "index_graph", "mcp"))


def _registered_package_lane(monkeypatch):
    import harness.plugins as plugins

    package_launch = _package_launch()
    monkeypatch.setattr(
        plugins, "plugin_execution_plan",
        lambda name: (package_launch, "lane", (), ()))


def test_catalog_restriction_pins_package_launch_to_explicit_workspace_root(
        tmp_path, monkeypatch):
    from harness.gateway_agent_mcp_cache import restricted_catalog_launch

    workspace = tmp_path / "workspace"
    workspace.mkdir()

    monkeypatch.setenv("FLYWHEEL_WORKSPACE_ROOT", str(workspace))
    _registered_package_lane(monkeypatch)

    launch, kind = restricted_catalog_launch("index", ["index.doctor"])

    assert kind == "lane"
    assert launch.cwd == str(workspace.resolve())
    assert launch.inherit_env is False
    assert launch.allowed_tools == ("index.doctor",)


def test_catalog_restriction_rejects_package_launch_without_explicit_workspace_root(
        monkeypatch):
    from harness.gateway_agent_mcp_cache import restricted_catalog_launch

    monkeypatch.delenv("FLYWHEEL_WORKSPACE_ROOT", raising=False)
    _registered_package_lane(monkeypatch)

    with pytest.raises(GatewayOperationError, match="MCP_CATALOG_LAUNCH_UNAVAILABLE"):
        restricted_catalog_launch("index", ["index.doctor"])


@pytest.mark.parametrize("workspace_root", ["~", "~/"])
def test_catalog_restriction_rejects_tilde_workspace_root(
        workspace_root, monkeypatch):
    from harness.gateway_agent_mcp_cache import restricted_catalog_launch

    monkeypatch.setenv("FLYWHEEL_WORKSPACE_ROOT", workspace_root)
    _registered_package_lane(monkeypatch)

    with pytest.raises(GatewayOperationError, match="MCP_CATALOG_LAUNCH_UNAVAILABLE"):
        restricted_catalog_launch("index", ["index.doctor"])

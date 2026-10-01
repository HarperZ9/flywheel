"""External-client mode cannot widen Articulate through argv or inherited env."""
import os
from types import SimpleNamespace

import pytest

from harness import bundled_lane_admission as bundled
from harness import bundled_lane_descriptor as descriptor


LOCAL_ARGS = ["--bundled-lane-mcp", "articulate", "--local-only"]


def test_restricted_environment_precedes_importability_and_serve(monkeypatch):
    monkeypatch.setenv("ARTICULATE_MCP_TOOLS", "all")
    monkeypatch.setenv("ARTICULATE_LOCAL_ONLY", "0")
    observed = []

    def observe(stage):
        observed.append((stage, os.environ["ARTICULATE_MCP_TOOLS"],
                         os.environ["ARTICULATE_LOCAL_ONLY"]))

    def importable(_name):
        observe("admit")
        return True

    def serve():  # Deliberately no **kwargs: --local-only is not a serve grant.
        observe("serve")
        return 0

    def import_module(name):
        assert name == "articulate.local_mcp"
        observe("import")
        return SimpleNamespace(serve=serve)

    monkeypatch.setattr(descriptor, "module_importable", importable)
    assert bundled.dispatch_bundled_lane_mcp(
        LOCAL_ARGS, import_module_fn=import_module,
        environ={"ARTICULATE_MCP_TOOLS": "all", "ARTICULATE_LOCAL_ONLY": "0"}) == 0
    assert observed == [(stage, "local", "1") for stage in ("admit", "import", "serve")]


@pytest.mark.parametrize("args", [
    ["--local-only"],
    ["--local-only", "--bundled-lane-mcp", "articulate"],
    ["--port", "0", *LOCAL_ARGS],
    ["--bundled-lane-mcp", "--local-only", "articulate"],
    [*LOCAL_ARGS, "--local-only"],
    [*LOCAL_ARGS, "--allow-exec"],
    ["--bundled-lane-mcp", "articulate", "--local-only=true"],
    ["--bundled-lane-mcp", "articulate", "--unknown"],
    ["--bundled-lane-mcp", "articulate", "extra", "--local-only"],
    ["--bundled-lane-mcp", "relay", "--local-only"],
    ["--bundled-lane-mcp", "forum", "--local-only", "--allow-gate-decisions"],
    ["--bundled-lane-mcp", "unregistered", "--local-only"],
])
def test_invalid_external_argv_refused_before_import(monkeypatch, args):
    def unexpected(*_args, **_kwargs):
        pytest.fail("invalid argv reached admission/import")

    monkeypatch.setattr(bundled, "admit_bundled_lane", unexpected)
    assert bundled.dispatch_bundled_lane_mcp(args, import_module_fn=unexpected) == 2


def test_legacy_internal_articulate_does_not_force_restricted_profile(monkeypatch):
    monkeypatch.setenv("ARTICULATE_MCP_TOOLS", "all")
    monkeypatch.setenv("ARTICULATE_LOCAL_ONLY", "0")
    monkeypatch.setattr(descriptor, "module_importable", lambda _name: True)

    def serve():
        assert os.environ["ARTICULATE_MCP_TOOLS"] == "all"
        assert os.environ["ARTICULATE_LOCAL_ONLY"] == "0"
        return 0

    assert bundled.dispatch_bundled_lane_mcp(
        ["--bundled-lane-mcp", "articulate"],
        import_module_fn=lambda _name: SimpleNamespace(serve=serve)) == 0


def test_normal_gateway_argv_is_not_claimed():
    assert bundled.dispatch_bundled_lane_mcp(["--port", "0"]) is None

"""Portable and compatibility manifests must describe the same local server."""
import json

import pytest

from claude_plugin_helpers import load

build = load("build_claude_plugin")
rules = load("claude_plugin_rules")
smoke = load("smoke_claude_plugin")


@pytest.fixture
def plugin(tmp_path):
    out = tmp_path / "plugin with spaces"
    build.build(out)
    return out


def test_portable_and_compatibility_bundle_passes(plugin):
    assert rules.check_portable(plugin) == []


@pytest.mark.parametrize("path,mutate", [
    ("plugin.json", lambda d: d.update(version="0.0.0")),
    ("plugin.json", lambda d: d.update(name="different-plugin")),
    ("plugin.json", lambda d: d.update(skills="./skills/")),
    (".codex-plugin/plugin.json", lambda d: d["interface"].update(displayName="Wrong")),
    ("mcp.json", lambda d: d["mcpServers"]["articulate"].pop("type")),
    ("mcp.json", lambda d: d["mcpServers"]["articulate"].update(type="streamable-http")),
    ("mcp.json", lambda d: d["mcpServers"]["articulate"]["args"].append("${CLAUDE_PLUGIN_ROOT}")),
    ("mcp.json", lambda d: d["mcpServers"]["articulate"]["env"].update(ARTICULATE_LOCAL_ONLY="0")),
    (".codex-mcp.json", lambda d: d["mcpServers"]["articulate"].update(cwd="..")),
])
def test_portable_rules_reject_drift(plugin, path, mutate):
    target = plugin / path
    data = json.loads(target.read_text(encoding="utf-8"))
    mutate(data)
    target.write_text(json.dumps(data), encoding="utf-8")
    assert rules.check_portable(plugin)


@pytest.mark.parametrize("host", ["portable", "codex"])
def test_each_launch_resolves_inside_plugin(plugin, host):
    argv, env = smoke.launch_spec(plugin, command="python-test", host=host)
    assert argv[-1] == (plugin / "server" / "serve.py").as_posix()
    assert env["ARTICULATE_LOCAL_ONLY"] == "1"
    assert not any("${" in arg for arg in argv)


@pytest.mark.parametrize("host", ["portable", "codex"])
def test_each_declared_launch_serves_and_guards_edits(plugin, host):
    import sys
    results, stderr = smoke.smoke(plugin, command=sys.executable, host=host)
    assert all(passed for _, passed, _ in results), (results, stderr)

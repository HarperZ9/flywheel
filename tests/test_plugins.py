"""The plugin registry must be honest and inert: every lane and the builtin
set appear in the roster, registration grants nothing and refuses reserved
or malformed entries, toggles persist, and probing a dead command reports
unreachable instead of inventing a tool list."""

import json

from harness import plugins


def _isolate(monkeypatch, tmp_path):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))


def test_roster_includes_lanes_and_builtins(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    doc = plugins.plugin_roster()
    names = {p["name"] for p in doc["plugins"]}
    assert {"gather", "crucible", "index", "forum", "learn", "telos",
            "local-model", "tools"} <= names
    builtin = next(p for p in doc["plugins"] if p["name"] == "tools")
    assert set(builtin["tools"]) == set(plugins.BUILTIN_TOOLS)
    assert "grants nothing" in doc["note"]


def test_register_refuses_reserved_and_malformed(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    assert "error" in plugins.register_mcp("gather", ["x"])
    assert "error" in plugins.register_mcp("tools", ["x"])
    assert "error" in plugins.register_mcp("", ["x"])
    assert "error" in plugins.register_mcp("mine", [])
    assert "error" in plugins.register_mcp("mine", "not-a-list")


def test_register_toggle_remove_roundtrip_persists(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    out = plugins.register_mcp("mine", ["mytool", "mcp"], "a test server")
    assert out["registered"] == "mine"
    # Duplicate refused.
    assert "error" in plugins.register_mcp("mine", ["other"])
    # Persisted on disk under FLYWHEEL_HOME.
    reg = json.loads((tmp_path / "plugins.json").read_text(encoding="utf-8"))
    assert reg["mcp"][0]["name"] == "mine"
    # Toggle off shows in the roster.
    assert plugins.toggle_mcp("mine", False)["enabled"] is False
    row = next(p for p in plugins.plugin_roster()["plugins"]
               if p["name"] == "mine")
    assert row["enabled"] is False
    # Disabled plugins refuse to probe.
    assert plugins.probe_plugin("mine")["status"] == "disabled"
    # Remove.
    assert plugins.remove_mcp("mine")["removed"] == "mine"
    assert "error" in plugins.toggle_mcp("mine", True)


def test_probe_dead_command_is_unreachable_not_invented(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    plugins.register_mcp("dead", ["definitely-not-a-real-command-xyz"])
    out = plugins.probe_plugin("dead", timeout=3.0)
    assert out["status"] == "unreachable"
    assert "tools" not in out


def test_probe_unknown_plugin_is_an_error(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    assert "error" in plugins.probe_plugin("nonexistent")


def test_builtin_probe_lists_gated_set(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    out = plugins.probe_plugin("tools")
    assert out["status"] == "live"
    assert set(out["tools"]) == set(plugins.BUILTIN_TOOLS)

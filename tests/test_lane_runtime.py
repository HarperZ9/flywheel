"""Explicit lane runtime selection."""
from __future__ import annotations
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

import harness.lanes as lanes
from harness.mcp_client import LaunchSpec


def _registry(monkeypatch, tmp_path, row):
    path = tmp_path / "lanes.json"
    path.write_text(json.dumps({"index": row}), encoding="utf-8")
    monkeypatch.setattr(lanes, "LANE_REGISTRY_PATH", path)


def _index_source(tmp_path):
    source = tmp_path / "workspace" / "public" / "index"
    package = source / "src" / "index_graph"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text('__version__ = "2.10.0"\n', encoding="utf-8")
    return source


def _fake_python(tmp_path):
    exe = tmp_path / ("python.exe" if os.name == "nt" else "python")
    exe.write_text("", encoding="utf-8")
    return exe


def _pin_package_runtime(monkeypatch, version):
    monkeypatch.setattr(lanes, "_package_runtime_version",
                        lambda lane, python: version, raising=False)
    monkeypatch.setattr(lanes, "_installed_version",
                        lambda lane: "current-env-ignored")


def _client(monkeypatch, *, tools=(), response=None, enter_error=None,
            call_error=None):
    seen = []

    class FakeClient:
        def __init__(self, launch, **kwargs):
            seen.append(launch)

        def __enter__(self):
            if enter_error:
                raise enter_error
            return self

        def __exit__(self, *args):
            return False

        def list_tools(self):
            return list(tools)

        def call_text(self, name, arguments):
            if call_error:
                raise call_error
            return dict(response or {"ok": True, "text": "{}"})

    monkeypatch.setattr("harness.mcp_client.MCPClient", FakeClient)
    return seen


def test_explicit_package_runtime_cannot_be_shadowed_by_source_checkout(
        tmp_path, monkeypatch):
    source = _index_source(tmp_path)
    python = _fake_python(tmp_path)
    _registry(monkeypatch, tmp_path, {
        "runtime_profile": "package",
        "runtime_version": "2.12.0",
        "runtime_python": str(python),
        "profile": "source",
        "version": "2.9.0",
    })
    monkeypatch.setattr(lanes, "resolve_source_repo", lambda lane: source)
    _pin_package_runtime(monkeypatch, "2.12.0")

    launch = lanes.resolve_mcp_launch("index")

    assert launch == LaunchSpec((str(python.resolve()), "-I", "-m", "index_graph", "mcp"))
    status = lanes.lane_status("index", probe=False)
    runtime = status["resolved_runtime"]
    assert runtime["selected_profile"] == "package"
    assert runtime["selected_runtime"] == "package"
    assert runtime["expected_version"] == "2.10.0"
    assert runtime["runtime_expected_version"] == "2.12.0"
    assert runtime["installed_version"] == "2.12.0"
    assert runtime["source_available"] is True
    assert runtime["source_selected"] is False
    assert runtime["capability"] == {"probed": False, "tool_count": None, "tool_names_sha256": None}
    encoded_runtime = json.dumps(runtime)
    assert str(python) not in encoded_runtime
    assert str(source) not in encoded_runtime
    assert runtime["launch"]["cwd_selected"] is False
    assert "PYTHONPATH" not in runtime["launch"]["env_override_keys"]
    assert runtime["mismatch_codes"] == []


def test_explicit_package_runtime_missing_fails_closed(tmp_path, monkeypatch):
    source = _index_source(tmp_path)
    python = _fake_python(tmp_path)
    _registry(monkeypatch, tmp_path, {
        "runtime_profile": "package",
        "runtime_version": "2.12.0",
        "runtime_python": str(python),
    })
    monkeypatch.setattr(lanes, "resolve_source_repo", lambda lane: source)
    _pin_package_runtime(monkeypatch, None)

    with pytest.raises(lanes.LaneRuntimeError, match="package_runtime_missing"):
        lanes.resolve_mcp_launch("index")

    runtime = lanes.lane_status("index", probe=False)["resolved_runtime"]
    assert runtime["selected_profile"] == "package"
    assert runtime["selected_runtime"] == "package"
    assert runtime["source_available"] is True
    assert runtime["source_selected"] is False
    assert runtime["installed_version"] is None
    assert "package_runtime_missing" in runtime["mismatch_codes"]


def test_explicit_package_version_mismatch_reports_observed_version(
        tmp_path, monkeypatch):
    source = _index_source(tmp_path)
    python = _fake_python(tmp_path)
    _registry(monkeypatch, tmp_path, {
        "runtime_profile": "package",
        "runtime_version": "2.12.0",
        "runtime_python": str(python),
    })
    monkeypatch.setattr(lanes, "resolve_source_repo", lambda lane: source)
    _pin_package_runtime(monkeypatch, "2.10.0")

    with pytest.raises(lanes.LaneRuntimeError, match="installed_version_mismatch"):
        lanes.resolve_mcp_launch("index")

    runtime = lanes.lane_status("index", probe=False)["resolved_runtime"]
    assert runtime["expected_version"] == "2.10.0"
    assert runtime["runtime_expected_version"] == "2.12.0"
    assert runtime["installed_version"] == "2.10.0"
    assert "installed_version_mismatch" in runtime["mismatch_codes"]


def test_missing_runtime_profile_keeps_legacy_auto_source_precedence(
        tmp_path, monkeypatch):
    source = _index_source(tmp_path)
    _registry(monkeypatch, tmp_path, {
        "profile": "package",
        "installed": True,
        "version": "2.9.0",
    })
    monkeypatch.setattr(lanes, "resolve_source_repo", lambda lane: source)
    monkeypatch.setattr(lanes, "_installed_version", lambda lane: "2.12.0")

    launch = lanes.resolve_mcp_launch("index")

    assert launch.argv == (sys.executable, "-m", "index_graph", "mcp")
    assert launch.cwd == str(source.resolve())
    assert dict(launch.env_overrides)["PYTHONPATH"].split(os.pathsep)[0] == str(
        (source / "src").resolve())
    runtime = lanes.lane_status("index", probe=False)["resolved_runtime"]
    assert runtime["selected_profile"] == "auto"
    assert runtime["selected_runtime"] == "source"
    assert runtime["selection_source"] == "default.auto"


def test_explicit_source_runtime_uses_source_even_when_package_is_present(
        tmp_path, monkeypatch):
    source = _index_source(tmp_path)
    _registry(monkeypatch, tmp_path, {"runtime_profile": "source"})
    monkeypatch.setattr(lanes, "resolve_source_repo", lambda lane: source)
    monkeypatch.setattr(lanes, "_installed_version", lambda lane: "2.12.0")

    launch = lanes.resolve_mcp_launch("index")

    assert launch.cwd == str(source.resolve())
    assert launch.argv == (sys.executable, "-m", "index_graph", "mcp")
    runtime = lanes.lane_status("index", probe=False)["resolved_runtime"]
    assert runtime["selected_profile"] == "source"
    assert runtime["selected_runtime"] == "source"


def test_invalid_runtime_profile_is_named_without_auto_fallback(tmp_path, monkeypatch):
    source = _index_source(tmp_path)
    secretish = "C:/Users/Zain/.ssh/private-profile-token"
    _registry(monkeypatch, tmp_path, {"runtime_profile": secretish})
    monkeypatch.setattr(lanes, "resolve_source_repo", lambda lane: source)
    monkeypatch.setattr(lanes, "_installed_version", lambda lane: "2.12.0")

    with pytest.raises(lanes.LaneRuntimeError, match="invalid_runtime_profile"):
        lanes.resolve_mcp_launch("index")

    runtime = lanes.lane_status("index", probe=False)["resolved_runtime"]
    assert runtime["selected_profile"] == "invalid"
    assert runtime["selected_runtime"] == "invalid"
    assert "invalid_runtime_profile" in runtime["mismatch_codes"]
    assert secretish not in json.dumps(runtime)


def test_probe_false_runtime_status_does_not_spawn_mcp(tmp_path, monkeypatch):
    _registry(monkeypatch, tmp_path, {"runtime_profile": "package"})
    monkeypatch.setattr(lanes, "resolve_source_repo", lambda lane: None)
    monkeypatch.setattr(lanes, "_installed_version", lambda lane: lane.version)

    class RefuseSpawn:
        def __init__(self, *args, **kwargs):
            raise AssertionError("probe=False spawned an MCP client")

    monkeypatch.setattr("harness.mcp_client.MCPClient", RefuseSpawn)
    runtime = lanes.lane_status("index", probe=False)["resolved_runtime"]
    assert runtime["capability"]["probed"] is False


def test_probe_true_records_bounded_capability_digest(tmp_path, monkeypatch):
    _registry(monkeypatch, tmp_path, {"runtime_profile": "package"})
    monkeypatch.setattr(lanes, "resolve_source_repo", lambda lane: None)
    monkeypatch.setattr(lanes, "_installed_version", lambda lane: lane.version)
    _client(monkeypatch, tools=[{"name": "index.context"}, {"name": "index.status"}])
    status = lanes.lane_status("index", probe=True, timeout=1.0)

    capability = status["resolved_runtime"]["capability"]
    expected = hashlib.sha256(
        json.dumps(["index.context", "index.status"], separators=(",", ":")).encode()
    ).hexdigest()
    assert capability == {"probed": True, "tool_count": 2, "tool_names_sha256": expected}


def test_probe_failure_detail_uses_safe_code_not_exception_text(
        tmp_path, monkeypatch):
    secretish = "C:/Users/Zain/.ssh/key"
    _registry(monkeypatch, tmp_path, {"runtime_profile": "package"})
    monkeypatch.setattr(lanes, "resolve_source_repo", lambda lane: None)
    monkeypatch.setattr(lanes, "_installed_version", lambda lane: lane.version)
    _client(monkeypatch, enter_error=OSError(f"could not open {secretish}"))

    status = lanes.lane_status("index", probe=True, timeout=1.0)

    assert status["status"] == lanes.DECLARED
    assert "mcp_probe_failed" in status["detail"]
    assert secretish not in json.dumps(status)


def test_health_tool_detail_uses_safe_codes_not_child_text(tmp_path, monkeypatch):
    from harness.mcp_client import MCPError

    secretish = "C:/Users/Zain/.ssh/key"
    _registry(monkeypatch, tmp_path, {"runtime_profile": "package"})
    monkeypatch.setattr(lanes, "resolve_source_repo", lambda lane: None)
    monkeypatch.setattr(lanes, "_installed_version", lambda lane: lane.version)
    _client(monkeypatch, tools=[{"name": "index.status"}],
            response={"ok": False, "text": f"not healthy: {secretish}"})
    status = lanes.lane_status("index", probe=True, timeout=1.0)
    assert status["status"] == lanes.STALE
    assert "health_tool_error" in status["detail"]
    assert secretish not in json.dumps(status)

    _client(monkeypatch, tools=[{"name": "index.status"}],
            call_error=MCPError(f"failed from {secretish}"))
    status = lanes.lane_status("index", probe=True, timeout=1.0)
    assert "health_tool_exception" in status["detail"]
    assert secretish not in json.dumps(status)


def test_lane_caller_uses_selected_runtime_launch(tmp_path, monkeypatch):
    from harness.lane_caller import call_lane_tool

    python = _fake_python(tmp_path)
    _registry(monkeypatch, tmp_path, {
        "runtime_profile": "package",
        "runtime_version": "2.12.0",
        "runtime_python": str(python),
    })
    monkeypatch.setattr(lanes, "resolve_source_repo", lambda lane: None)
    _pin_package_runtime(monkeypatch, "2.12.0")
    seen = _client(monkeypatch, response={"ok": True, "text": '{"ok": true}'})
    assert call_lane_tool("index", "index.status") == {"ok": True}
    assert seen == [LaunchSpec((str(python.resolve()), "-I", "-m", "index_graph", "mcp"))]


def test_context_envelope_uses_selected_runtime_launch(tmp_path, monkeypatch):
    from harness.context_envelope import build_context_envelope

    python = _fake_python(tmp_path)
    _registry(monkeypatch, tmp_path, {
        "runtime_profile": "package",
        "runtime_version": "2.12.0",
        "runtime_python": str(python),
    })
    monkeypatch.setattr(lanes, "resolve_source_repo", lambda lane: None)
    _pin_package_runtime(monkeypatch, "2.12.0")
    seen = _client(monkeypatch, tools=[{"name": "index.context.envelope"}],
                   response={"ok": True, "text": '{"retained_names":["index"]}'})
    build_context_envelope(".", lane_timeout=1.0)
    assert seen == [LaunchSpec((str(python.resolve()), "-I", "-m", "index_graph", "mcp"))]

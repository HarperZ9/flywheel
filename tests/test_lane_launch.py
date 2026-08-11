"""Lane launch resolution + failure diagnosability.

A pip lane's console script is only as healthy as the interpreter its shim was
built for; a stale shim made every lane read `unreachable` with a bare "server
closed the connection" while the real cause (ModuleNotFoundError) went to a
discarded stderr. These tests keep public commands portable, runtime launches
source-aware, frozen launches bare, and unreachable stderr visible."""
import os
import sys

import harness.lanes as ln
import harness.plugins as pl
from harness.mcp_client import LaunchSpec
from harness.plugins import probe_plugin


def test_public_pip_command_stays_portable_when_importable(monkeypatch):
    monkeypatch.setattr(ln, "_importable", lambda top: True)
    cmd = ln.resolve_mcp_command("gather")
    assert cmd == ["gather", "mcp"]


def test_runtime_pip_lane_prefers_this_interpreter_when_importable(monkeypatch):
    monkeypatch.setattr(ln, "resolve_source_repo", lambda lane: None)
    monkeypatch.setattr(ln, "_importable", lambda top: True)
    launch = ln.resolve_mcp_launch("gather")
    assert launch == LaunchSpec((sys.executable, "-m", "gather.cli", "mcp"))


def test_runtime_pip_lane_falls_back_to_console_script(monkeypatch):
    monkeypatch.setattr(ln, "resolve_source_repo", lambda lane: None)
    monkeypatch.setattr(ln, "_importable", lambda top: False)
    launch = ln.resolve_mcp_launch("gather")
    assert launch == LaunchSpec(("gather", "mcp"))


def test_importable_checks_top_package_only(monkeypatch):
    seen = []
    monkeypatch.setattr(ln, "_importable",
                        lambda top: (seen.append(top), False)[1])
    monkeypatch.setattr(ln, "resolve_source_repo", lambda lane: None)
    ln.resolve_mcp_launch("gather")
    assert seen == ["gather"]                # never the dotted submodule


def test_bundled_lane_runs_in_this_interpreter():
    launch = ln.resolve_mcp_launch("local-model")
    assert launch.argv[0] == sys.executable
    assert launch.argv[1:] == ("-m", "harness.local_mcp")


def test_python_source_launch_has_child_cwd_and_pythonpath(
        tmp_path, monkeypatch):
    source = tmp_path / "public" / "gather"
    source.mkdir(parents=True)
    monkeypatch.setattr(ln, "resolve_source_repo", lambda lane: source)
    monkeypatch.setattr(ln, "_importable", lambda top: False)
    monkeypatch.setenv("PYTHONPATH", "existing-path")
    launch = ln.resolve_mcp_launch("gather")
    assert launch.argv == (sys.executable, "-m", "gather.cli", "mcp")
    assert launch.cwd == str(source.resolve())
    assert dict(launch.env_overrides)["PYTHONPATH"] == (
        str(source.resolve()) + os.pathsep + "existing-path")


def test_python_source_launch_precedes_importable_package(tmp_path, monkeypatch):
    source = tmp_path / "public" / "gather"
    source.mkdir(parents=True)
    monkeypatch.setattr(ln, "resolve_source_repo", lambda lane: source)
    monkeypatch.setattr(ln, "_importable", lambda top: True)
    monkeypatch.setenv("PYTHONPATH", "installed-path")
    launch = ln.resolve_mcp_launch("gather")
    assert launch.argv == (sys.executable, "-m", "gather.cli", "mcp")
    assert launch.cwd == str(source.resolve())
    assert dict(launch.env_overrides)["PYTHONPATH"] == (
        str(source.resolve()) + os.pathsep + "installed-path")


def test_node_source_launch_uses_absolute_script(tmp_path, monkeypatch):
    source = tmp_path / "public" / "telos"
    (source / "demo").mkdir(parents=True)
    (source / "demo" / "telos-mcp.mjs").write_text("", encoding="utf-8")
    monkeypatch.setattr(ln, "resolve_source_repo", lambda lane: source)
    launch = ln.resolve_mcp_launch("telos")
    assert launch == LaunchSpec(("node", str((source / "demo" / "telos-mcp.mjs").resolve())))


def test_unreachable_probe_reports_server_stderr(monkeypatch):
    # A real subprocess that dies at launch the way a stale shim does: one
    # line of stderr, nonzero exit, nothing on stdout.
    crash = [sys.executable, "-c",
             "import sys; sys.stderr.write('ModuleNotFoundError: no lane\\n');"
             "sys.exit(3)"]
    monkeypatch.setattr(pl, "LANES", {"deadlane"}, raising=False)
    monkeypatch.setattr(pl, "resolve_mcp_launch", lambda name: LaunchSpec(tuple(crash)))
    out = probe_plugin("deadlane", timeout=15.0)
    assert out["status"] == "unreachable"
    assert "server stderr" in out["detail"]
    assert "ModuleNotFoundError: no lane" in out["detail"]


def test_unreachable_probe_without_stderr_stays_plain(monkeypatch):
    quiet = [sys.executable, "-c", "raise SystemExit(0)"]
    monkeypatch.setattr(pl, "LANES", {"quietlane"}, raising=False)
    monkeypatch.setattr(pl, "resolve_mcp_launch", lambda name: LaunchSpec(tuple(quiet)))
    out = probe_plugin("quietlane", timeout=15.0)
    assert out["status"] == "unreachable"
    assert "server stderr" not in out["detail"]   # no words, no fabricated words


def test_frozen_build_never_launches_sys_executable(monkeypatch):
    # In a PyInstaller bundle sys.executable IS the gateway; using it as a
    # Python would relaunch the gateway instead of a lane server.
    monkeypatch.setattr(ln, "_frozen", lambda: True)
    monkeypatch.setattr(ln, "_importable", lambda top: True)  # even if importable
    for name in ln.LANES:
        launch = ln.resolve_mcp_launch(name)
        assert launch.argv[0] != sys.executable, f"{name} would relaunch the gateway"


def test_frozen_pip_lane_uses_console_script(monkeypatch):
    monkeypatch.setattr(ln, "_frozen", lambda: True)
    monkeypatch.setattr(ln, "_importable", lambda top: True)
    assert ln.resolve_mcp_launch("gather") == LaunchSpec(("gather", "mcp"))


def test_frozen_node_lane_keeps_bare_declared_command(tmp_path, monkeypatch):
    monkeypatch.setattr(ln, "_frozen", lambda: True)
    monkeypatch.setattr(ln, "resolve_source_repo", lambda lane: tmp_path)
    assert ln.resolve_mcp_launch("telos") == LaunchSpec(
        ("node", "demo/telos-mcp.mjs"))


def test_gateway_forum_proxy_uses_runtime_launch_spec(monkeypatch):
    import harness.gateway as gateway
    import harness.mcp_client as mcp_client

    expected = LaunchSpec(("forum-runtime",), "/source")
    seen = []

    class FakeClient:
        def __init__(self, launch, **kwargs):
            seen.append(launch)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def call_text(self, tool, arguments):
            return {"ok": True, "text": '{"status":"ok"}'}

    monkeypatch.setattr(ln, "resolve_mcp_launch", lambda name: expected,
                        raising=False)
    monkeypatch.setattr(mcp_client, "MCPClient", FakeClient)
    assert gateway._forum_mcp_call("forum.status", {}) == {"status": "ok"}
    assert seen == [expected]

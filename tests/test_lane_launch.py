"""Lane launch resolution + failure diagnosability.

A pip lane's console script is only as healthy as the interpreter its shim was
built for; a stale shim made every lane read `unreachable` with a bare "server
closed the connection" while the real cause (ModuleNotFoundError) went to a
discarded stderr. These tests hold the two fixes: resolve_mcp_command prefers
the engine's own interpreter when it can import the lane, and an unreachable
probe reports the server's own stderr."""
import sys

import harness.lanes as ln
import harness.plugins as pl
from harness.plugins import probe_plugin


def test_pip_lane_prefers_this_interpreter_when_importable(monkeypatch):
    monkeypatch.setattr(ln, "_importable", lambda top: True)
    cmd = ln.resolve_mcp_command("gather")
    assert cmd == [sys.executable, "-m", "gather.cli", "mcp"]


def test_pip_lane_falls_back_to_console_script(monkeypatch):
    monkeypatch.setattr(ln, "_importable", lambda top: False)
    cmd = ln.resolve_mcp_command("gather")
    assert cmd == ["gather", "mcp"]          # the historical PATH behavior


def test_importable_checks_top_package_only(monkeypatch):
    seen = []
    monkeypatch.setattr(ln, "_importable",
                        lambda top: (seen.append(top), False)[1])
    ln.resolve_mcp_command("gather")         # py_module is gather.cli
    assert seen == ["gather"]                # never the dotted submodule


def test_bundled_lane_runs_in_this_interpreter():
    cmd = ln.resolve_mcp_command("local-model")
    assert cmd[0] == sys.executable          # not whichever `python` wins PATH
    assert cmd[1:] == ["-m", "harness.local_mcp"]


def test_unreachable_probe_reports_server_stderr(monkeypatch):
    # A real subprocess that dies at launch the way a stale shim does: one
    # line of stderr, nonzero exit, nothing on stdout.
    crash = [sys.executable, "-c",
             "import sys; sys.stderr.write('ModuleNotFoundError: no lane\\n');"
             "sys.exit(3)"]
    monkeypatch.setattr(pl, "LANES", {"deadlane"}, raising=False)
    monkeypatch.setattr(pl, "resolve_mcp_command", lambda name: crash)
    out = probe_plugin("deadlane", timeout=15.0)
    assert out["status"] == "unreachable"
    assert "server stderr" in out["detail"]
    assert "ModuleNotFoundError: no lane" in out["detail"]


def test_unreachable_probe_without_stderr_stays_plain(monkeypatch):
    quiet = [sys.executable, "-c", "raise SystemExit(0)"]
    monkeypatch.setattr(pl, "LANES", {"quietlane"}, raising=False)
    monkeypatch.setattr(pl, "resolve_mcp_command", lambda name: quiet)
    out = probe_plugin("quietlane", timeout=15.0)
    assert out["status"] == "unreachable"
    assert "server stderr" not in out["detail"]   # no words, no fabricated words


def test_frozen_build_never_hands_out_sys_executable(monkeypatch):
    # In a PyInstaller bundle sys.executable IS the gateway; using it as a
    # Python would relaunch the gateway instead of a lane server.
    monkeypatch.setattr(ln, "_frozen", lambda: True)
    monkeypatch.setattr(ln, "_importable", lambda top: True)  # even if importable
    for name in ln.LANES:
        cmd = ln.resolve_mcp_command(name)
        assert cmd[0] != sys.executable, f"{name} would relaunch the gateway"


def test_frozen_pip_lane_uses_console_script(monkeypatch):
    monkeypatch.setattr(ln, "_frozen", lambda: True)
    monkeypatch.setattr(ln, "_importable", lambda top: True)
    assert ln.resolve_mcp_command("gather") == ["gather", "mcp"]

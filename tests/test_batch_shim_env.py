"""A batch file the harness starts cannot run a program planted in its working folder.

On Windows a resolved ``.cmd`` runs inside cmd.exe, and cmd.exe looks up every
bare name the script runs in its working folder before PATH. npm's shim for a
globally installed tool (an LSP server, an MCP server, codex) runs ``node`` that
way whenever node.exe does not sit beside the shim, which is the default Node.js
layout. Resolving the ``.cmd`` safely is then not enough: a ``node.bat`` in the
folder the shim runs in answers for node. Each site here starts a real shim,
with the Windows opt-out variable removed as on a default install, from a
working folder that holds such a plant; the plant must not run. The first test
is the control: the same shim started with the caller's environment runs it.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.name != "nt", reason="cmd.exe batch lookup")

SHIM = """@ECHO off
GOTO start
:find_dp0
SET dp0=%~dp0
EXIT /b
:start
SETLOCAL
CALL :find_dp0

IF EXIST "%dp0%\\node.exe" (
  SET "_prog=%dp0%\\node.exe"
) ELSE (
  SET "_prog=node"
  SET PATHEXT=%PATHEXT:;.JS;=;%
)

endLocal & goto #_undefined_# 2>NUL || title %COMSPEC% & "%_prog%"  "%dp0%\\cli.js" %*
"""


@pytest.fixture
def shim(tmp_path, monkeypatch):
    """(working folder holding a planted node.bat, marker it writes)."""
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    for name in ("fwshim", "npm", "codex", "buildc"):
        (bin_ / f"{name}.cmd").write_text(SHIM.replace("\n", "\r\n"), encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()
    marker = tmp_path / "planted-node-ran.txt"
    (work / "node.bat").write_text(f'@echo ran> "{marker}"\r\n', encoding="utf-8")
    root = os.environ.get("SystemRoot", "C:\\Windows")
    monkeypatch.setenv("PATH", os.pathsep.join((str(bin_), os.path.join(root, "System32"))))
    monkeypatch.delenv("NoDefaultCurrentDirectoryInExePath", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path / "fwhome"))
    monkeypatch.chdir(work)
    return work, marker


def _finish(result):
    """Wait for whatever a site started, so the marker is final."""
    proc = result[0] if isinstance(result, tuple) else result
    proc = getattr(proc, "proc", None) or getattr(proc, "process", None) or proc
    if isinstance(proc, subprocess.Popen):
        try:
            proc.communicate(timeout=20)
        except (subprocess.TimeoutExpired, ValueError):
            proc.kill()


def test_control_the_shim_runs_the_plant_with_the_callers_environment(shim):
    from harness import safe_program
    work, marker = shim
    subprocess.run(safe_program.argv(["fwshim"], cwd=work), cwd=work, capture_output=True,
                   timeout=20)
    assert marker.exists(), "control: cmd.exe looked up node in the shim's working folder"


def _dap_pid(work):
    from harness.dap_policy import _spawn_detached
    pid = _spawn_detached(["fwshim"], work, None)
    import time
    for _ in range(100):
        if (work.parent / "planted-node-ran.txt").exists():
            break
        time.sleep(0.05)
    return pid


def _mcp(spec: bool):
    from harness.mcp_client import LaunchSpec, StdioTransport
    work = Path.cwd()
    return StdioTransport(LaunchSpec(("fwshim", "serve"), cwd=str(work)) if spec
                          else ["fwshim", "serve"])


SITES = {
    "stdio protocol server": lambda w: __import__(
        "harness.child_stdio", fromlist=["x"]).spawn(["fwshim", "--stdio"], w),
    "debug adapter launch": _dap_pid,
    "cli endpoint": lambda w: __import__("harness.endpoints", fromlist=["x"]).CliBackend(
        "probe", ["fwshim", "{prompt}"], cwd=str(w)).chat(
            [{"role": "user", "content": "hi"}], system="", max_tokens=1,
            temperature=0.0, seed=0),
    "accountable hook": lambda w: __import__(
        "harness.accountable_hooks", fromlist=["x"]).subprocess_runner()(["fwshim"]),
    "command authority": lambda w: __import__(
        "harness.authority_registry", fromlist=["x"])._command_resolver(
            {"argv": ["fwshim"]}, w, True, 20.0, None)("answer"),
    "verified bench gate": lambda w: __import__(
        "harness.verified_bench", fromlist=["x"]).subprocess_gate(
            "fwshim --check", "proposal", workspace=w),
    "mcp launch spec": lambda w: _mcp(True),
    "mcp argv": lambda w: _mcp(False),
    "buildc receipt verify": lambda w: __import__(
        "harness.buildc_receipt_bridge", fromlist=["x"]).run_buildc_verify(w / "r.json"),
    "killable argv": lambda w: __import__(
        "harness.lean_replay", fromlist=["x"]).run_killable(["fwshim"], timeout=20),
    "npm global root": lambda w: __import__(
        "harness.lane_runtime_support", fromlist=["x"])._npm_global_root.__wrapped__(),
    "codex app server": lambda w: __import__(
        "harness.codex_app_server_client", fromlist=["x"]).CodexAppServerStdioTransport(),
}


@pytest.mark.parametrize("site", sorted(SITES))
def test_a_batch_program_does_not_run_a_plant_from_its_working_folder(site, shim):
    work, marker = shim
    try:
        _finish(SITES[site](work))
    except Exception:
        pass  # the marker is the evidence
    assert not marker.exists(), f"{site}: the shim ran the node.bat planted in its folder"

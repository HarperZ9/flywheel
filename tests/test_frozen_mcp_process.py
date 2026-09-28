"""Frozen stdio MCP process runner must use the Windows Job launcher safely."""
from __future__ import annotations

import ctypes
import json
import os
import sys
from ctypes import wintypes
from pathlib import Path

import pytest


def _child_env(home: Path) -> dict[str, str]:
    env = {}
    for key in ("SystemRoot", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "OS"):
        if key in os.environ:
            env[key] = os.environ[key]
    temp = home / "tmp"
    temp.mkdir(parents=True, exist_ok=True)
    env.update({"TEMP": str(temp), "TMP": str(temp), "PYTHONUTF8": "1"})
    return env


def _script(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def _expect_error(code: str, func, *args, **kwargs):
    with pytest.raises(RuntimeError) as excinfo:
        func(*args, **kwargs)
    assert excinfo.value.args == (code,)


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object subprocess fixture")
def test_run_mcp_process_feeds_wire_on_stdin_until_eof(tmp_path):
    from scripts.frozen_mcp_process import run_mcp_process

    home = tmp_path / "home"
    home.mkdir()
    script = _script(tmp_path / "stdio_echo.py", """
import json, sys
wire = sys.stdin.read()
print(json.dumps({"wire": wire, "argv": sys.argv[1:]}), flush=True)
""")

    output = run_mcp_process(
        Path(sys.executable), ["-I", "-B", str(script), "sentinel"], home,
        _child_env(home), '{"jsonrpc":"2.0"}\n', timeout=10, max_bytes=2000)

    payload = json.loads(output)
    assert payload == {"wire": '{"jsonrpc":"2.0"}\n', "argv": ["sentinel"]}


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object subprocess fixture")
def test_run_mcp_process_refuses_any_stderr_without_leaking_text(tmp_path):
    from scripts.frozen_mcp_process import run_mcp_process

    home = tmp_path / "home"
    home.mkdir()
    script = _script(tmp_path / "stderr.py", """
import sys
print("visible stdout")
print("private stderr path C:/operator/secret", file=sys.stderr)
""")

    _expect_error(
        "MCP_STDERR", run_mcp_process, Path(sys.executable), ["-I", "-B", str(script)],
        home, _child_env(home), "", timeout=10, max_bytes=2000)


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object subprocess fixture")
def test_run_mcp_process_terminates_oversized_stdout_while_polling(tmp_path):
    from scripts.frozen_mcp_process import run_mcp_process

    home = tmp_path / "home"
    home.mkdir()
    script = _script(tmp_path / "oversized.py", """
import sys, time
for _ in range(40):
    sys.stdout.write("x" * 128)
    sys.stdout.flush()
    time.sleep(0.01)
""")

    _expect_error(
        "MCP_STDOUT_OVERSIZED", run_mcp_process, Path(sys.executable),
        ["-I", "-B", str(script)], home, _child_env(home), "", timeout=10,
        max_bytes=512)


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object subprocess fixture")
def test_run_mcp_process_rejects_descendant_stdout_after_parent_exit(tmp_path):
    from scripts.frozen_mcp_process import run_mcp_process

    home = tmp_path / "home"
    home.mkdir()
    descendant = _script(tmp_path / "late_stdout.py", """
import sys, time
time.sleep(0.2)
sys.stdout.write("x" * 2048)
sys.stdout.flush()
""")
    parent = _script(tmp_path / "parent_exit_stdout.py", f"""
import subprocess, sys
subprocess.Popen([sys.executable, "-I", "-B", {str(descendant)!r}])
""")

    _expect_error(
        "MCP_STDOUT_OVERSIZED", run_mcp_process, Path(sys.executable),
        ["-I", "-B", str(parent)], home, _child_env(home), "", timeout=10,
        max_bytes=512)


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object subprocess fixture")
def test_run_mcp_process_rejects_descendant_stderr_after_parent_exit(tmp_path):
    from scripts.frozen_mcp_process import run_mcp_process

    home = tmp_path / "home"
    home.mkdir()
    descendant = _script(tmp_path / "late_stderr.py", """
import sys, time
time.sleep(0.2)
print("private late stderr", file=sys.stderr, flush=True)
""")
    parent = _script(tmp_path / "parent_exit_stderr.py", f"""
import subprocess, sys
subprocess.Popen([sys.executable, "-I", "-B", {str(descendant)!r}])
""")

    _expect_error(
        "MCP_STDERR", run_mcp_process, Path(sys.executable),
        ["-I", "-B", str(parent)], home, _child_env(home), "", timeout=10,
        max_bytes=2000)


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object subprocess fixture")
def test_run_mcp_process_timeout_kills_descendant_job_member(tmp_path):
    from scripts.frozen_mcp_process import run_mcp_process

    home = tmp_path / "home"
    home.mkdir()
    descendant = tmp_path / "descendant.py"
    _script(descendant, """
import time
time.sleep(60)
""")
    pid_file = tmp_path / "descendant.pid"
    pid_part = tmp_path / "descendant.pid.part"
    # The 0.5s timeout can kill the spawner mid-write, so record the pid through a
    # temporary file and os.replace. The pid file is then either absent or complete,
    # never a truncated read that turns a timing window into int('').
    script = _script(tmp_path / "spawner.py", f'''
import os, subprocess, sys, time
child = subprocess.Popen([sys.executable, "-I", "-B", {str(descendant)!r}])
with open({str(pid_part)!r}, "w", encoding="utf-8") as handle:
    handle.write(str(child.pid))
    handle.flush()
    os.fsync(handle.fileno())
os.replace({str(pid_part)!r}, {str(pid_file)!r})
time.sleep(60)
''')

    _expect_error(
        "MCP_TIMEOUT", run_mcp_process, Path(sys.executable), ["-I", "-B", str(script)],
        home, _child_env(home), "", timeout=0.5, max_bytes=2000)

    recorded = pid_file.read_text(encoding="utf-8").strip() if pid_file.exists() else ""
    if recorded:
        assert not _pid_is_live(int(recorded))


def test_run_mcp_process_fails_closed_when_job_objects_unavailable(tmp_path, monkeypatch):
    from scripts import frozen_mcp_process

    monkeypatch.setattr(frozen_mcp_process.os, "name", "posix", raising=False)

    _expect_error(
        "MCP_WINDOWS_REQUIRED", frozen_mcp_process.run_mcp_process,
        Path(sys.executable), ["--version"], tmp_path, {}, "")


def _pid_is_live(pid: int) -> bool:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    kernel.GetExitCodeProcess.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.OpenProcess(0x1000, False, int(pid))
    if not handle:
        return False
    try:
        code = wintypes.DWORD()
        if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value == 259
    finally:
        kernel.CloseHandle(handle)

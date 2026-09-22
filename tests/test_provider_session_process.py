import io
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

from harness import provider_session_process as proc_owner


class FakeProc:
    def __init__(self):
        self._handle = 17
        self.pid = 1234
        self.stdin = io.BytesIO()
        self.stdout = io.BytesIO()
        self.stderr = io.BytesIO()
        self.returncode = None
        self.killed = False

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.returncode = 0 if self.returncode is None else self.returncode
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -9


class FakeApi:
    def __init__(self, events):
        self.events = events

    def CloseHandle(self, handle):
        self.events.append(("close-handle", handle))
        return True


def test_non_windows_fails_closed_before_spawn(tmp_path, monkeypatch):
    monkeypatch.setattr(proc_owner.os, "name", "posix", raising=False)
    monkeypatch.setattr(proc_owner.sys, "platform", "linux", raising=False)

    def forbidden_popen(*_args, **_kwargs):
        raise AssertionError("spawned without robust containment")

    monkeypatch.setattr(proc_owner.subprocess, "Popen", forbidden_popen)

    with pytest.raises(proc_owner.ProviderSessionProcessError) as exc:
        proc_owner.start_provider_session_process(
            ["provider.exe"], cwd=tmp_path, env={})

    assert "containment unavailable" in str(exc.value)
    assert "provider.exe" not in str(exc.value)


def test_launch_assigns_job_before_resume_and_exposes_binary_stdio(
        tmp_path, monkeypatch):
    events = []
    fake = FakeProc()
    seen = {}
    monkeypatch.setattr(proc_owner.os, "name", "nt", raising=False)
    monkeypatch.setattr(proc_owner.sys, "platform", "win32", raising=False)
    monkeypatch.setattr(proc_owner.subprocess, "CREATE_NO_WINDOW", 0x08000000,
                        raising=False)
    monkeypatch.setattr(proc_owner.subprocess, "CREATE_NEW_PROCESS_GROUP",
                        0x200, raising=False)

    def popen(argv, **kwargs):
        events.append(("popen", tuple(argv)))
        seen.update(kwargs)
        return fake

    monkeypatch.setattr(proc_owner.subprocess, "Popen", popen)
    monkeypatch.setattr(proc_owner.boundary, "_windows_job",
                        lambda p: events.append(("job", p)) or
                        (FakeApi(events), "job-handle"))
    monkeypatch.setattr(proc_owner.boundary, "_resume_windows",
                        lambda p: events.append(("resume", p)) or True)

    owned = proc_owner.start_provider_session_process(
        ["provider.exe", "--stdio"], cwd=tmp_path, env={"A": "B"})

    try:
        assert events[:3] == [
            ("popen", ("provider.exe", "--stdio")),
            ("job", fake),
            ("resume", fake),
        ]
        assert seen["cwd"] == str(tmp_path)
        assert seen["env"] == {"A": "B"}
        assert seen["shell"] is False
        assert seen["stdin"] == subprocess.PIPE
        assert seen["stdout"] == subprocess.PIPE
        assert seen["stderr"] == subprocess.PIPE
        assert seen["close_fds"] is True
        assert seen["creationflags"] & 0x4
        assert seen["creationflags"] & 0x08000000
        assert owned.stdin is fake.stdin
        assert owned.stdout is fake.stdout
        assert owned.pid == 1234
    finally:
        owned.close()


def test_resume_failure_terminates_with_sanitized_error(tmp_path, monkeypatch):
    fake = FakeProc()
    terminated = []
    monkeypatch.setattr(proc_owner.os, "name", "nt", raising=False)
    monkeypatch.setattr(proc_owner.sys, "platform", "win32", raising=False)
    monkeypatch.setattr(proc_owner.subprocess, "CREATE_NO_WINDOW", 0x08000000,
                        raising=False)
    monkeypatch.setattr(proc_owner.subprocess, "CREATE_NEW_PROCESS_GROUP",
                        0x200, raising=False)
    monkeypatch.setattr(proc_owner.subprocess, "Popen",
                        lambda *_args, **_kwargs: fake)
    monkeypatch.setattr(proc_owner.boundary, "_windows_job",
                        lambda _p: (FakeApi([]), "job-handle"))
    monkeypatch.setattr(proc_owner.boundary, "_resume_windows",
                        lambda _p: False)
    monkeypatch.setattr(proc_owner.boundary, "_terminate_unowned",
                        lambda p: terminated.append(p))

    with pytest.raises(proc_owner.ProviderSessionProcessError) as exc:
        proc_owner.start_provider_session_process(
            ["secret-provider.exe"], cwd=tmp_path,
            env={"TOKEN": "secret-value"})

    assert terminated == [fake]
    assert "resume failed" in str(exc.value)
    assert "secret" not in str(exc.value).lower()


def test_persistent_binary_stdio_acceptance(tmp_path):
    _windows_only()
    code = (
        "import sys\n"
        "for line in sys.stdin.buffer:\n"
        "    sys.stdout.buffer.write(b'echo:' + line)\n"
        "    sys.stdout.buffer.flush()\n"
    )
    owned = proc_owner.start_provider_session_process(
        [sys.executable, "-u", "-c", code], cwd=tmp_path, env=_child_env())
    try:
        owned.stdin.write(b"one\n"); owned.stdin.flush()
        assert _readline(owned.stdout) == b"echo:one\n"
        owned.stdin.write(b"two\n"); owned.stdin.flush()
        assert _readline(owned.stdout) == b"echo:two\n"
    finally:
        cleanup = owned.close(timeout_s=2)
    assert cleanup.exited is True
    assert cleanup.stderr_raw is None


def test_bounded_stderr_drain_does_not_block_stdout(tmp_path):
    _windows_only()
    code = (
        "import sys, time\n"
        "sys.stderr.buffer.write(b'x' * 262144)\n"
        "sys.stderr.buffer.flush()\n"
        "sys.stdout.buffer.write(b'ready\\n')\n"
        "sys.stdout.buffer.flush()\n"
        "sys.stdin.buffer.readline()\n"
    )
    owned = proc_owner.start_provider_session_process(
        [sys.executable, "-u", "-c", code], cwd=tmp_path, env=_child_env(),
        stderr_limit=64)
    try:
        assert _readline(owned.stdout) == b"ready\n"
    finally:
        cleanup = owned.close(timeout_s=2)
    assert cleanup.stderr_observed_bytes >= 262144
    assert cleanup.stderr_truncated is True
    assert cleanup.stderr_raw is None


def test_close_kills_synthetic_grandchild_tree(tmp_path):
    _windows_only()
    grandchild = (
        "import time\n"
        "time.sleep(60)\n"
    )
    parent = (
        "import json, os, subprocess, sys, time\n"
        "grand = subprocess.Popen([sys.executable, '-c', %r])\n"
        "print(json.dumps({'parent': os.getpid(), 'grandchild': grand.pid}),"
        " flush=True)\n"
        "time.sleep(60)\n"
    ) % grandchild
    owned = proc_owner.start_provider_session_process(
        [sys.executable, "-u", "-c", parent], cwd=tmp_path, env=_child_env())
    line = _readline(owned.stdout)
    pids = json.loads(line.decode("utf-8"))
    assert _pid_alive(pids["grandchild"])

    cleanup = owned.close(timeout_s=3)

    assert cleanup.exited is True
    assert _eventually_not_alive(pids["parent"])
    assert _eventually_not_alive(pids["grandchild"])


def _windows_only():
    if os.name != "nt":
        pytest.skip("Windows Job Object acceptance only")


def _child_env():
    keep = {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "PATH", "TEMP",
            "TMP"}
    env = {k: v for k, v in os.environ.items() if k.upper() in keep}
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _readline(pipe, timeout=5):
    result = []
    worker = threading.Thread(target=lambda: result.append(pipe.readline()),
                              daemon=True)
    worker.start()
    worker.join(timeout)
    assert result, "timed out waiting for child stdout"
    return result[0]


def _pid_alive(pid):
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL,
                                   wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE,
                                          ctypes.POINTER(wintypes.DWORD))
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
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


def _eventually_not_alive(pid, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            return True
        time.sleep(0.05)
    return not _pid_alive(pid)

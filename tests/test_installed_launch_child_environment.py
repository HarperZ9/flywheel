"""Minimal child environment must support Winsock without inheriting secrets."""
import ctypes
import json
import os
import sys
from ctypes import wintypes
from pathlib import Path

import pytest

from desktop.tool.installed_launch_acceptance_model import build_child_environment


ALLOWED = {
    "SystemRoot": r"C:\Windows",
    "WINDIR": r"C:\Windows",
    "COMSPEC": r"C:\Windows\System32\cmd.exe",
    "PATHEXT": ".COM;.EXE;.BAT;.CMD",
    "OS": "Windows_NT",
    "PROCESSOR_ARCHITECTURE": "AMD64",
    "PROCESSOR_IDENTIFIER": "Intel64 Family 6 Model 142 Stepping 12, GenuineIntel",
    "PROCESSOR_LEVEL": "6",
    "PROCESSOR_REVISION": "8e0c",
    "NUMBER_OF_PROCESSORS": "8",
}


@pytest.mark.parametrize("casing", ["upper", "lower", "mixed"])
def test_allowed_names_retain_original_spelling_and_values_in_any_case(tmp_path, casing):
    def spell(name):
        if casing == "mixed":
            return "".join(c.lower() if i % 2 else c.upper() for i, c in enumerate(name))
        return getattr(name, casing)()

    base = {spell(key): value for key, value in ALLOWED.items()}
    before = dict(base)
    child = build_child_environment(base, tmp_path / "isolated")

    assert {key: child.get(key) for key in base} == before
    assert base == before
    assert len(child) == len(base) + 4


def test_filter_excludes_secrets_proxy_path_and_replaces_parent_profile(tmp_path):
    base = {
        "SYSTEMROOT": r"C:\Windows",
        "OPENAI_API_KEY": "synthetic-provider-secret",
        "fLyWhEeL_tOkEn": "synthetic-gateway-secret",
        "HTTPS_PROXY": "http://proxy.example.invalid:8080",
        "http_proxy": "http://proxy.example.invalid:8080",
        "ALL_PROXY": "socks5://proxy.example.invalid:1080",
        "NO_PROXY": "internal.example.invalid",
        "Path": r"C:\untrusted-tools",
        "PYTHONPATH": r"C:\untrusted-modules",
        "SYSTEMROOT_EXTRA": r"C:\untrusted-windows",
        "FLYWHEEL_HOME": r"C:\operator-state",
        "USERPROFILE": r"C:\Users\operator",
        "TEMP": r"C:\operator-temp",
        "tmp": r"C:\operator-temp",
    }
    before = dict(base)
    root = (tmp_path / "isolated profile").resolve()

    child = build_child_environment(base, root)

    assert child == {
        "SYSTEMROOT": r"C:\Windows",
        "FLYWHEEL_HOME": str(root / "home"),
        "USERPROFILE": str(root / "user"),
        "TEMP": str(root / "tmp"),
        "TMP": str(root / "tmp"),
    }
    assert base == before
    assert {p.name for p in root.iterdir()} == {"home", "user", "tmp"}
    assert all(p.is_dir() for p in root.iterdir())


def test_empty_parent_environment_creates_only_isolated_directories(tmp_path):
    root = (tmp_path / "empty parent").resolve()
    child = build_child_environment({}, root)

    assert child == {
        "FLYWHEEL_HOME": str(root / "home"),
        "USERPROFILE": str(root / "user"),
        "TEMP": str(root / "tmp"),
        "TMP": str(root / "tmp"),
    }
    assert all(Path(value).is_dir() for value in child.values())


@pytest.mark.skipif(os.name != "nt", reason="Windows os.environ key normalization")
def test_real_windows_environment_preserves_systemroot_without_parent_mutation(tmp_path):
    before = dict(os.environ)
    assert "SYSTEMROOT" in before

    child = build_child_environment(os.environ, tmp_path / "real environment")

    assert child.get("SYSTEMROOT") == before["SYSTEMROOT"]
    parent_unchanged = dict(os.environ) == before
    assert parent_unchanged, "Filtering must not mutate the real parent environment"


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object and Winsock integration")
@pytest.mark.parametrize("explicit_systemroot_control", [False, True], ids=["filtered", "control"])
def test_owned_python_can_bind_loopback_and_job_cleanup_closes_handles(
        tmp_path, explicit_systemroot_control):
    from desktop.tool.installed_launch_acceptance_jobs import start_windows_job_process

    child_env = build_child_environment(os.environ, tmp_path / "profile")
    if explicit_systemroot_control:
        # Independent positive control: supplying the required OS variable directly
        # distinguishes environment regression from a broken socket fixture.
        child_env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    stdout, stderr = tmp_path / "stdout.json", tmp_path / "stderr.log"
    script = """
import json, socket, sys
try:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', 0))
        print(json.dumps({'host': sock.getsockname()[0], 'port': sock.getsockname()[1]}))
except OSError as exc:
    code = exc.winerror or exc.errno or 1
    print(json.dumps({'winerror': code}))
    sys.exit(code)
"""
    process, error = start_windows_job_process(
        Path(sys.executable), ["-I", "-B", "-c", script], child_env, tmp_path, stdout, stderr)
    assert error == ""
    assert process is not None
    try:
        wait_code = process.kernel.WaitForSingleObject(process.process.hProcess, 10000)
        exit_code = wintypes.DWORD()
        get_exit = process.kernel.GetExitCodeProcess
        get_exit.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        get_exit.restype = wintypes.BOOL
        exit_read = bool(get_exit(process.process.hProcess, ctypes.byref(exit_code)))
    finally:
        cleanup = process.terminate_and_verify(timeout_ms=5000)

    assert cleanup["state"] == "PASS", cleanup
    assert cleanup["job_active_pids_after"] == []
    assert cleanup["job_handles_closed"] is True
    assert wait_code == 0, "Python fixture exceeded the fixed 10-second deadline"
    assert exit_read is True
    assert exit_code.value == 0, stdout.read_text(encoding="utf-8")
    assert stderr.read_text(encoding="utf-8") == ""
    bound = json.loads(stdout.read_text(encoding="utf-8"))
    assert bound["host"] == "127.0.0.1"
    assert 0 < bound["port"] <= 65535

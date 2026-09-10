import json
import os
import shutil
import socket
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from desktop.tool import installed_launch_acceptance as ila
from desktop.tool import installed_launch_acceptance_platform as platform
from tests.installed_launch_acceptance_fixtures import (
    COMMIT, build_manifest, make_install, run_harness, valid_receipt,
)


def _write_receipt(path: Path, body) -> None:
    path.write_text(json.dumps(body), encoding="utf-8")


def test_python_receipt_semantics_rejects_nonobject_rows_with_receipt_error(tmp_path):
    cases = {
        "assertion-string": lambda b: b["assertions"].__setitem__(0, "bad-row"),
        "assertion-list-id": lambda b: b["assertions"][0].update({"id": ["H01"]}),
        "phase-string": lambda b: b["phase_results"].__setitem__(0, "bad-row"),
        "phase-list-id": lambda b: b["phase_results"][0].update({"id": ["P0"]}),
    }
    for name, mutate in cases.items():
        body = valid_receipt()
        mutate(body)
        path = tmp_path / f"{name}.json"
        _write_receipt(path, body)
        with pytest.raises(ila.ReceiptError, match="semantic validation failed"):
            ila.verify_receipt_file(path, "run-a")


def test_nonobject_build_manifest_is_typed_h20_failure_not_crash(tmp_path):
    install, app_sha, engine_sha = make_install(tmp_path)
    manifest = tmp_path / "manifest.json"
    manifest.write_text("[]", encoding="utf-8")

    receipt = run_harness(
        tmp_path, install, build_manifest=manifest,
        expected_app_sha256=app_sha, expected_engine_sha256=engine_sha,
    )

    observed = next(
        row for row in receipt["assertions"]
        if row["id"] == "H20_receipt_fresh_complete_and_source_bound"
    )["observed_redacted"]
    assert receipt["complete"] is False
    assert ila.assertion_state(receipt, "H20_receipt_fresh_complete_and_source_bound") == "FAIL"
    assert "build_manifest_malformed:non_object" in observed["binding_failures"]


def test_wrapper_selftest_covers_json_valid_bad_rows_and_list_ids():
    repo = Path(__file__).parents[1]
    script = repo / "desktop" / "tool" / "run_installed_launch_acceptance.ps1"
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-SelfTest"],
        cwd=repo, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert completed.returncode == 0, completed.stderr
    cases = {case["name"]: case["message"] for case in json.loads(completed.stdout)["cases"]}
    assert {
        "zero-exit-nonobject-assertion-row",
        "zero-exit-list-assertion-id",
        "zero-exit-nonobject-phase-row",
        "zero-exit-list-phase-id",
    }.issubset(cases)
    assert "id is not a string" in cases["zero-exit-list-assertion-id"]
    assert "id is not a string" in cases["zero-exit-list-phase-id"]


def _windows_powershell() -> str | None:
    system_root = os.environ.get("SystemRoot")
    if system_root:
        candidate = Path(system_root) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        if candidate.exists():
            return str(candidate)
    return shutil.which("powershell")


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell wrapper path test")
def test_wrapper_preserves_spaced_paths_and_sanitizes_failure_stderr(tmp_path):
    powershell = _windows_powershell()
    if powershell is None:
        pytest.skip("powershell unavailable")
    repo = Path(__file__).parents[1]
    install, app_sha, engine_sha = make_install(tmp_path / "Program Files")
    manifest_dir = tmp_path / "manifest dir"
    manifest_dir.mkdir()
    manifest = build_manifest(manifest_dir, install, app_sha=app_sha, engine_sha=engine_sha)
    validation = tmp_path / "validation out"
    out = validation / "receipt out.json"
    script = repo / "desktop" / "tool" / "run_installed_launch_acceptance.ps1"

    completed = subprocess.run(
        [
            powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
            "-InstallRoot", str(install), "-ValidationDir", str(validation), "-Out", str(out),
            "-RunId", "space-run", "-SourceCommitExpected", COMMIT, "-ExpectedVersion", "0.6.1",
            "-ExpectedAppSha256", app_sha, "-ExpectedEngineSha256", engine_sha,
            "-BuildManifest", str(manifest),
        ],
        cwd=repo, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )

    assert completed.returncode != 0
    assert out.exists()
    child_stderr = validation / "installed-launch-acceptance.stderr.log"
    assert "unrecognized arguments" not in child_stderr.read_text(encoding="utf-8", errors="replace")
    assert str(repo) not in completed.stderr
    assert str(script) not in completed.stderr


def _pid_is_running(pid: int) -> bool:
    if os.name != "nt":
        return False
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    kernel.GetExitCodeProcess.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    try:
        code = wintypes.DWORD()
        return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
    finally:
        kernel.CloseHandle(handle)


def _reserve_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object cleanup test")
def test_job_cleanup_kills_child_created_after_initial_descendant_snapshot(tmp_path):
    marker = tmp_path / "spawn child.flag"
    child_pid = tmp_path / "child pid.txt"
    stdout, stderr = tmp_path / "parent.out", tmp_path / "parent.err"
    child_code = "import time; time.sleep(60)"
    parent_code = textwrap.dedent("""
        import pathlib, subprocess, sys, time
        marker = pathlib.Path(sys.argv[1])
        pidfile = pathlib.Path(sys.argv[2])
        code = sys.argv[3]
        deadline = time.time() + 10
        while not marker.exists() and time.time() < deadline:
            time.sleep(0.02)
        child = subprocess.Popen([sys.executable, "-c", code])
        pidfile.write_text(str(child.pid), encoding="utf-8")
        time.sleep(60)
    """)

    class LateSnapshotController(platform.LocalProcessController):
        def __init__(self):
            super().__init__()
            self.triggered = False

        def descendant_processes(self, pid):
            rows = super().descendant_processes(pid)
            if not self.triggered:
                self.triggered = True
                marker.write_text("go", encoding="utf-8")
                end = time.monotonic() + 5
                while time.monotonic() < end and not child_pid.exists():
                    time.sleep(0.02)
                assert child_pid.exists(), "late child did not start"
                return []
            return rows

    controller = LateSnapshotController()
    keep = {"SystemRoot", "WINDIR", "COMSPEC", "PATHEXT", "OS"}
    env = {key: value for key, value in os.environ.items() if key in keep}
    handle = controller.start_engine(
        Path(sys.executable),
        ["-c", parent_code, str(marker), str(child_pid), child_code],
        env, tmp_path, stdout, stderr,
    )
    assert handle.job_object_assigned, handle.job_error
    try:
        result = controller.cleanup(handle, _reserve_port())
    finally:
        if handle.pid:
            controller._stop_pids([handle.pid])
    pid = int(child_pid.read_text(encoding="utf-8"))
    assert result["state"] == "PASS"
    assert result["job_active_pids_after"] == []
    assert result["job_handles_closed"] is True
    assert not _pid_is_running(pid)

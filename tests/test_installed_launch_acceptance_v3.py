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
    COMMIT, build_manifest, make_install, powershell_for_selftest, run_harness, valid_receipt,
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
        [powershell_for_selftest(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-SelfTest"],
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
            "-PythonPath", sys.executable,
            "-InstallRoot", str(install), "-ValidationDir", str(validation), "-Out", str(out),
            "-RunId", "space-run", "-SourceCommitExpected", COMMIT, "-ExpectedVersion", "0.6.1",
            "-ExpectedAppSha256", app_sha, "-ExpectedEngineSha256", engine_sha,
            "-BuildManifest", str(manifest),
        ],
        cwd=repo, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )

    assert completed.returncode != 0
    assert out.exists()
    receipt = json.loads(out.read_text(encoding="utf-8"))
    assert receipt["source_commit_expected"] == COMMIT
    assert ila.assertion_state(receipt, "H20_receipt_fresh_complete_and_source_bound") == "FAIL"
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
@pytest.mark.parametrize("publication", ["direct", "gated"])
def test_job_cleanup_kills_child_created_after_initial_descendant_snapshot(
        tmp_path, monkeypatch, text_once_written, publication):
    marker = tmp_path / "spawn child.flag"
    child_pid = tmp_path / "child pid.txt"
    publish = tmp_path / "publish pid.flag"
    empty_reads = []
    original_read = Path.read_text

    def observe_pid_read(path, *args, **kwargs):
        value = original_read(path, *args, **kwargs)
        if path == child_pid and publication == "gated" and not value:
            empty_reads.append(value)
            publish.write_text("publish", encoding="utf-8")
        return value

    monkeypatch.setattr(Path, "read_text", observe_pid_read)
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
        assert marker.exists(), "snapshot did not release child"
        child = subprocess.Popen([sys.executable, "-c", code])
        with pidfile.open("w", encoding="utf-8") as stream:
            if sys.argv[4] == "gated":
                release = pathlib.Path(sys.argv[5])
                deadline = time.monotonic() + 10
                while not release.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                assert release.exists(), "PID publication was never released"
            stream.write(str(child.pid))
        time.sleep(60)
    """)

    class LateSnapshotController(platform.LocalProcessController):
        def __init__(self):
            super().__init__()
            self.triggered = False
            self.late_pid = None

        def descendant_processes(self, pid):
            rows = super().descendant_processes(pid)
            if not self.triggered:
                self.triggered = True
                marker.write_text("go", encoding="utf-8")
                self.late_pid = int(text_once_written(
                    child_pid, timeout=5, why="late child did not publish its PID"))
                assert self.late_pid > 0 and self.late_pid != pid
                assert _pid_is_running(self.late_pid), "late child was not alive before cleanup"
                active, query_error = handle.proc.active_pids()
                assert not query_error and self.late_pid in active
                return []
            return rows

    controller = LateSnapshotController()
    keep = {"SystemRoot", "WINDIR", "COMSPEC", "PATHEXT", "OS"}
    env = {key: value for key, value in os.environ.items() if key in keep}
    handle = controller.start_engine(
        Path(sys.executable),
        ["-c", parent_code, str(marker), str(child_pid), child_code,
         publication, str(publish)],
        env, tmp_path, stdout, stderr,
    )
    try:
        assert handle.job_object_assigned, handle.job_error
        result = controller.cleanup(handle, _reserve_port())
        pid = controller.late_pid
        assert result["state"] == "PASS"
        assert result["job_active_pids_after"] == []
        assert result["job_handles_closed"] is True
        assert not _pid_is_running(pid), "late child survived cleanup"
        if publication == "gated":
            assert empty_reads, "control did not observe the empty publication window"
    finally:
        if handle.proc is not None and not handle.proc.handles_closed:
            handle.proc.terminate_and_verify()


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object cleanup test")
def test_late_child_fixture_rejects_forged_cleanup_success(
        tmp_path, monkeypatch, text_once_written):
    monkeypatch.setattr(platform.LocalProcessController, "_cleanup_job",
                        lambda *args: {"state": "PASS", "job_active_pids_after": [],
                                       "job_handles_closed": True})
    with pytest.raises(AssertionError, match="late child survived cleanup"):
        test_job_cleanup_kills_child_created_after_initial_descendant_snapshot(
            tmp_path, monkeypatch, text_once_written, "gated")
    pid = int((tmp_path / "child pid.txt").read_text(encoding="utf-8"))
    assert not _pid_is_running(pid), "fallback did not clean up the negative control"

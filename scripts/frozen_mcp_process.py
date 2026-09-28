"""Bounded stdio runner for frozen MCP acceptance checks on Windows."""
from __future__ import annotations

import ctypes
import os
import time
import uuid
from ctypes import wintypes
from pathlib import Path
from typing import Mapping, Sequence

from desktop.tool.installed_launch_acceptance_jobs import (
    WAIT_OBJECT_0,
    WAIT_TIMEOUT,
    start_windows_job_process,
)


POLL_SECONDS = 0.05
POLL_MILLISECONDS = int(POLL_SECONDS * 1000)
JOB_DRAIN_SECONDS = 1.0


def run_mcp_process(executable: Path | str, args: Sequence[str], home: Path | str,
                    env: Mapping[str, str], wire: str | bytes, timeout: float = 30,
                    max_bytes: int = 2_000_000) -> str:
    """Run a frozen stdio MCP command through the existing Windows Job launcher."""
    if os.name != "nt":
        _fail("MCP_WINDOWS_REQUIRED")
    if timeout <= 0 or max_bytes <= 0:
        _fail("MCP_LIMIT_INVALID")

    root = Path(home).resolve()
    root.mkdir(parents=True, exist_ok=True)
    run_dir = _new_run_dir(root)
    stdin_path = run_dir / "stdin.jsonl"
    stdout_path = run_dir / "stdout.txt"
    stderr_path = run_dir / "stderr.txt"
    stdin_bytes = wire.encode("utf-8") if isinstance(wire, str) else bytes(wire)
    if len(stdin_bytes) > max_bytes:
        _fail("MCP_STDIN_OVERSIZED")
    stdin_path.write_bytes(stdin_bytes)

    process, error = start_windows_job_process(
        Path(executable), [str(arg) for arg in args], dict(env), run_dir,
        stdout_path, stderr_path, stdin_path=stdin_path)
    if error or process is None:
        _fail("MCP_JOB_START")

    try:
        _wait_for_exit_or_limit(process, stdout_path, stderr_path, timeout, max_bytes)
        exit_code = _exit_code(process)
        _check_output_limits(process, stdout_path, stderr_path, max_bytes)
        if exit_code != 0:
            _cleanup_then_fail(process, "MCP_EXIT")
        active, query_error = _wait_job_empty(
            process, stdout_path, stderr_path, max_bytes)
        if query_error or active:
            _cleanup_then_fail(process, "MCP_JOB_ACTIVE")
        stdout_size = _check_output_limits(
            process, stdout_path, stderr_path, max_bytes)
        output = _read_stdout_text(process, stdout_path, stdout_size, max_bytes)
        if not process.close():
            _fail("MCP_JOB_CLOSE")
        return output
    except Exception:
        if not getattr(process, "handles_closed", True):
            process.terminate_and_verify(timeout_ms=5000)
        raise


def _wait_for_exit_or_limit(process, stdout: Path, stderr: Path, timeout: float,
                            max_bytes: int) -> None:
    deadline = time.monotonic() + timeout
    while True:
        wait_code = process.kernel.WaitForSingleObject(
            process.process.hProcess, POLL_MILLISECONDS)
        if _file_size(stdout) > max_bytes:
            _cleanup_then_fail(process, "MCP_STDOUT_OVERSIZED")
        if _file_size(stderr) > max_bytes:
            _cleanup_then_fail(process, "MCP_STDERR_OVERSIZED")
        if wait_code == WAIT_OBJECT_0:
            return
        if wait_code != WAIT_TIMEOUT:
            _cleanup_then_fail(process, "MCP_WAIT_FAILED")
        if time.monotonic() >= deadline:
            cleanup = process.terminate_and_verify(timeout_ms=5000)
            if cleanup.get("state") != "PASS":
                _fail("MCP_TIMEOUT_CLEANUP")
            _fail("MCP_TIMEOUT")


def _check_output_limits(process, stdout: Path, stderr: Path, max_bytes: int) -> int:
    stdout_size = _file_size(stdout)
    stderr_size = _file_size(stderr)
    if stdout_size > max_bytes:
        _cleanup_then_fail(process, "MCP_STDOUT_OVERSIZED")
    if stderr_size > max_bytes:
        _cleanup_then_fail(process, "MCP_STDERR_OVERSIZED")
    if stderr_size:
        _cleanup_then_fail(process, "MCP_STDERR")
    return stdout_size


def _cleanup_then_fail(process, code: str) -> None:
    cleanup = process.terminate_and_verify(timeout_ms=5000)
    if cleanup.get("state") != "PASS" and code not in {
        "MCP_STDOUT_OVERSIZED", "MCP_STDERR_OVERSIZED", "MCP_STDERR",
    }:
        _fail("MCP_JOB_CLEANUP")
    _fail(code)


def _exit_code(process) -> int:
    get_exit = process.kernel.GetExitCodeProcess
    get_exit.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    get_exit.restype = wintypes.BOOL
    code = wintypes.DWORD()
    if not get_exit(process.process.hProcess, ctypes.byref(code)):
        _cleanup_then_fail(process, "MCP_EXIT_READ")
    return int(code.value)


def _wait_job_empty(process, stdout: Path, stderr: Path,
                    max_bytes: int) -> tuple[list[int], str]:
    deadline = time.monotonic() + JOB_DRAIN_SECONDS
    last_active: list[int] = []
    while True:
        _check_output_limits(process, stdout, stderr, max_bytes)
        active, query_error = process.active_pids()
        _check_output_limits(process, stdout, stderr, max_bytes)
        if query_error or not active:
            return active, query_error
        last_active = active
        if time.monotonic() >= deadline:
            return last_active, ""
        time.sleep(POLL_SECONDS)


def _read_stdout_text(process, stdout: Path, expected_size: int, max_bytes: int) -> str:
    with open(stdout, "rb") as stream:
        data = stream.read(max_bytes + 1)
    if len(data) > max_bytes:
        _cleanup_then_fail(process, "MCP_STDOUT_OVERSIZED")
    if len(data) != expected_size or _file_size(stdout) != expected_size:
        _cleanup_then_fail(process, "MCP_STDOUT_GROWTH")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        _fail("MCP_STDOUT_TEXT")


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except FileNotFoundError:
        return 0


def _new_run_dir(home: Path) -> Path:
    base = home / "frozen-mcp-process"
    base.mkdir(parents=True, exist_ok=True)
    for _ in range(10):
        candidate = base / uuid.uuid4().hex
        try:
            candidate.mkdir()
            return candidate
        except FileExistsError:
            continue
    _fail("MCP_RUN_DIR_COLLISION")


def _fail(code: str):
    raise RuntimeError(code) from None

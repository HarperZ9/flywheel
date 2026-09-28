"""Shipped lookups never find a program planted in the working folder, and the
oracle's shell never runs one.

Each program here exists only as a plant: in the working folder, and on POSIX
behind a relative PATH entry. 1.1.0 asked shutil.which, which on Windows looks in
the working folder first and on POSIX follows a relative entry, so every lookup
below found the plant and reported the tool as present. Each case first checks
that shutil.which does see the plant, so a pass is not an unreachable plant.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

WINDOWS = os.name == "nt"
ORIGINAL_PATH = os.environ.get("PATH", "")
windows_only = pytest.mark.skipif(not WINDOWS, reason="Windows system tools")


def _plant(folder: Path, name: str, body: str = "exit 0") -> Path:
    path = folder / (f"{name}.exe" if WINDOWS else name)
    path.write_bytes(b"MZ" if WINDOWS else f"#!/bin/sh\n{body}\n".encode())
    path.chmod(0o755)
    return path


@pytest.fixture
def work(tmp_path, monkeypatch):
    folder = tmp_path / "work"
    folder.mkdir()
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.chdir(folder)
    monkeypatch.delenv("NoDefaultCurrentDirectoryInExePath", raising=False)
    monkeypatch.setenv("PATH", os.pathsep.join(([] if WINDOWS else ["."]) + [str(empty)]))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    return folder


def _lane_cli_gather():
    from harness import lane_cli
    return lane_cli.lane_cli_argv("gather", frozen=False, importable=lambda _top: False)


def _find_git():
    from harness import tool_discovery
    return tool_discovery.find_git({"PATH": "."}, read_registry_path=lambda _scope: None).found


def _claude():
    from harness import claude_cli_auth
    return claude_cli_auth.resolve_official_cli().get("cli_present")


def _codex():
    from harness.codex_consumer_backend import CodexConsumerBackend
    return CodexConsumerBackend(client_factory=lambda: 1 / 0).readiness()["cli_present"]


LOOKUPS = {
    "proof run lean": ("lean", lambda: __import__("harness.proof_run", fromlist=["x"]).lean_path()),
    "lean oracle": ("lean", lambda: __import__("harness.lean_oracle", fromlist=["x"])._lean_exe()),
    "manim": ("manimgl", lambda: __import__("harness.manim_lesson", fromlist=["x"])._manimgl_argv()),
    "endpoint credential": ("fwcli", lambda: __import__(
        "harness.endpoint_registry", fromlist=["x"])._credential(
            "", local=False, kind="cli", name="fwcli") == "cli-auth"),
    "endpoint health": ("fwcli", lambda: __import__(
        "harness.endpoints", fromlist=["x"]).CliBackend("x", ["fwcli"]).health()),
    "cross-harness binary": ("fwcli", lambda: __import__(
        "harness.cross_harness_cli_identity", fromlist=["x"]).resolve_binary(("fwcli",))),
    "hook interpreter": ("fwcli", lambda: __import__(
        "harness.trace_doctor_mounts", fromlist=["x"])._interpreter_problem("fwcli") == ""),
    "lane dev cli": ("gather", _lane_cli_gather),
    "sandbox backend": ("bwrap", lambda: __import__(
        "harness.posix_sandbox", fromlist=["x"]).backend_for("linux")),
    "tool discovery git": ("git", _find_git),
    "claude cli": ("claude", _claude),
    "codex cli": ("codex", _codex),
}


@pytest.mark.parametrize("site", sorted(LOOKUPS))
def test_the_lookup_does_not_find_a_plant(site, work):
    name, lookup = LOOKUPS[site]
    _plant(work, name)
    assert shutil.which(name) or site == "tool discovery git", "control: the plant is reachable"
    assert not lookup(), f"{site} found the planted {name}"


@pytest.mark.parametrize("tool", ["taskkill.exe", "icacls.exe", "wevtutil.exe", "wsl.exe"])
@windows_only
def test_a_windows_system_tool_is_the_system32_copy(tool, work, monkeypatch):
    from harness import safe_program
    (work / tool).write_bytes(b"MZ")
    seen = []
    monkeypatch.setattr(subprocess, "run", lambda args, *a, **k: seen.append(args) or (
        subprocess.CompletedProcess(args, 0, stdout=b"", stderr=b"")))
    monkeypatch.setenv("USERNAME", "probe")
    calls = {
        "taskkill.exe": lambda: __import__("harness.proc_kill", fromlist=["x"])._kill_tree(
            type("P", (), {"pid": 0})()),
        "icacls.exe": lambda: __import__("harness.receipt_signer", fromlist=["x"])._lock_down(
            work / "key"),
        "wevtutil.exe": lambda: __import__("harness.trace_witness", fromlist=["x"])
        .WindowsEventLogSink().read(),
        "wsl.exe": lambda: __import__("harness.training_lane", fromlist=["x"]).screen_alive(),
    }
    try:
        calls[tool]()
    except Exception:
        pass
    root = os.environ.get("SystemRoot", "C:\\Windows")
    assert seen and not isinstance(seen[0], str), f"{tool} ran as {seen!r}"
    assert os.path.normcase(seen[0][0]) == os.path.normcase(os.path.join(root, "System32", tool))
    assert safe_program.system_tool(tool) == seen[0][0]


@windows_only
def test_windows_hello_asks_the_system32_powershell(work):
    from harness.trace_presence_verifiers import WindowsHelloVerifier
    seen = []
    WindowsHelloVerifier(runner=lambda argv, **kw: seen.append(argv) or (
        subprocess.CompletedProcess(argv, 1, stdout=b"", stderr=b""))).ask("probe")
    root = os.environ.get("SystemRoot", "C:\\Windows")
    expected = os.path.join(root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    assert os.path.normcase(seen[0][0]) == os.path.normcase(expected)


def test_the_oracle_shell_does_not_run_a_python_planted_beside_the_candidate(tmp_path, work,
                                                                            monkeypatch):
    """A candidate's folder holding `python` must not answer the oracle's own
    `python ...` command: that plant could print a passing result."""
    from harness.oracle import PytestOracle
    marker = tmp_path / "planted-ran.txt"
    if WINDOWS:
        (work / "python.cmd").write_text(f'@echo ran> "{marker}"\r\n', encoding="utf-8")
    else:
        _plant(work, "python", f'echo ran > "{marker}"')
    # The real PATH, plus on POSIX the relative entry that reaches the folder.
    monkeypatch.setenv("PATH", os.pathsep.join(([] if WINDOWS else ["."]) + [ORIGINAL_PATH]))
    PytestOracle(timeout=30)._run("python --version", str(work))
    assert not marker.exists(), "the oracle's shell ran the planted python"


def test_the_oracle_shell_skips_a_path_entry_inside_the_task_folder(tmp_path, work,
                                                                   monkeypatch):
    """The engine runs elsewhere; PATH names a folder inside the task folder (a
    candidate's own bin). Its planted python must not answer the oracle."""
    from harness.oracle import PytestOracle
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    marker = tmp_path / "planted-ran.txt"
    tools = work / "tools"
    tools.mkdir()
    if WINDOWS:
        (tools / "python.cmd").write_text(f'@echo ran> "{marker}"\r\n', encoding="utf-8")
    else:
        _plant(tools, "python", f'echo ran > "{marker}"')
    monkeypatch.setenv("PATH", os.pathsep.join((str(tools), ORIGINAL_PATH)))
    assert shutil.which("python") and Path(shutil.which("python")).parent == tools, \
        "control: the plant is first on PATH"
    PytestOracle(timeout=30)._run("python --version", str(work))
    assert not marker.exists(), "the oracle's shell ran the python planted in the task folder"

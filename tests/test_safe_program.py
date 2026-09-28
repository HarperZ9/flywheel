"""safe_program: a bare program name never resolves to a copy planted in the working folder.

Each case plants a program that writes a marker when it runs, first shows the
unguarded lookup (shutil.which, a shell) finding or running it, and then shows
the guarded lookup refusing it. The first half is the control: without it a
pass could mean the plant was never reachable at all. The Windows opt-out
variable is removed first, since a default Windows install does not set it.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from harness import safe_program

WINDOWS = os.name == "nt"
NO_CWD = "NoDefaultCurrentDirectoryInExePath"
windows_only = pytest.mark.skipif(not WINDOWS, reason="a Windows lookup rule")


def plant(folder: Path, name: str, marker: Path) -> Path:
    """An executable ``name`` in ``folder`` that writes ``marker`` when started."""
    folder.mkdir(parents=True, exist_ok=True)
    if WINDOWS:
        path = folder / f"{name}.cmd"
        path.write_text(f'@echo ran> "{marker}"\r\n', encoding="utf-8")
    else:
        path = folder / name
        path.write_text(f'#!/bin/sh\necho ran > "{marker}"\n', encoding="utf-8")
        path.chmod(0o755)
    return path


def same(a, b) -> bool:
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def link_folder(link: Path, target: Path) -> None:
    if WINDOWS:
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
    else:
        link.symlink_to(target, target_is_directory=True)


@pytest.fixture
def work(tmp_path, monkeypatch):
    folder = tmp_path / "work"
    folder.mkdir()
    monkeypatch.chdir(folder)
    monkeypatch.delenv(NO_CWD, raising=False)
    return folder


def test_a_program_planted_in_the_working_folder_is_not_found(work, tmp_path, monkeypatch):
    marker = tmp_path / "ran.txt"
    plant(work, "fwplant", marker)
    empty = tmp_path / "empty"
    empty.mkdir()
    # Windows searches the working folder before PATH; POSIX does through ".".
    monkeypatch.setenv("PATH", str(empty) if WINDOWS else os.pathsep.join((".", str(empty))))
    assert shutil.which("fwplant"), "control: the unguarded lookup must see the plant"
    assert safe_program.which("fwplant") is None
    with pytest.raises(safe_program.ProgramUnavailable) as caught:
        safe_program.argv(["fwplant", "--version"])
    assert caught.value.code == "NOT_FOUND"
    assert isinstance(caught.value, FileNotFoundError)
    assert not marker.exists()


def test_a_linked_path_entry_into_the_working_folder_is_skipped(work, tmp_path, monkeypatch):
    marker = tmp_path / "ran.txt"
    plant(work / "sub", "fwplant", marker)
    link = tmp_path / "link"
    link_folder(link, work / "sub")
    monkeypatch.setenv("PATH", str(link))
    assert shutil.which("fwplant"), "control: the link reaches the plant"
    assert safe_program.which("fwplant") is None


@windows_only
def test_a_drive_relative_path_entry_is_skipped(work, tmp_path, monkeypatch):
    marker = tmp_path / "ran.txt"
    plant(work / "sub", "fwplant", marker)
    drive = Path.cwd().drive
    monkeypatch.setenv("PATH", f"{drive}sub")
    assert shutil.which("fwplant"), "control: C:sub means the sub folder of C:'s current folder"
    assert safe_program.which("fwplant") is None


@windows_only
def test_a_name_holding_a_drive_colon_is_refused(work):
    with pytest.raises(safe_program.ProgramUnavailable) as caught:
        safe_program.resolve(f"{Path.cwd().drive}fwplant")
    assert caught.value.code == "BAD_PATH"


def test_the_program_on_path_still_resolves_past_a_plant(work, tmp_path, monkeypatch):
    plant(work, "fwtool", tmp_path / "planted.txt")
    real = plant(tmp_path / "bin", "fwtool", tmp_path / "real.txt")
    monkeypatch.setenv("PATH", os.pathsep.join((".", str(tmp_path / "bin"))))
    found = safe_program.which("fwtool")
    assert found is not None and same(found, real)
    argv = safe_program.argv(["fwtool", "--flag"])
    assert same(argv[0], real) and argv[1:] == ["--flag"]


def test_a_shell_child_does_not_run_a_plant_in_its_working_folder(work, tmp_path, monkeypatch):
    marker = tmp_path / "ran.txt"
    plant(work, "fwplant", marker)
    monkeypatch.setenv("FW_KEEP_ME", "kept")
    unguarded = dict(os.environ)
    if not WINDOWS:
        unguarded["PATH"] = os.pathsep.join((".", unguarded.get("PATH", "")))
    subprocess.run("fwplant", shell=True, cwd=work, env=unguarded, capture_output=True)
    assert marker.exists(), "control: the shell ran the plant from its working folder"
    marker.unlink()
    env = safe_program.shell_env(unguarded, cwd=work)
    subprocess.run("fwplant", shell=True, cwd=work, env=env, capture_output=True)
    assert not marker.exists()
    assert env["FW_KEEP_ME"] == "kept"
    if WINDOWS:
        assert env[NO_CWD] == "1"
    else:
        assert "." not in env["PATH"].split(os.pathsep)


@windows_only
def test_a_batch_program_with_cmd_metacharacters_is_refused(work, tmp_path, monkeypatch):
    plant(tmp_path / "bin", "fwtool", tmp_path / "ran.txt")
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    assert safe_program.argv(["fwtool", "plain", "C:\\Program Files (x86)\\x"])
    with pytest.raises(safe_program.ProgramRefused) as caught:
        safe_program.argv(["fwtool", "a&calc"])
    assert caught.value.code == "UNSAFE_ARGUMENT"
    assert isinstance(caught.value, OSError)


@windows_only
def test_an_explicit_extension_must_match(work, tmp_path, monkeypatch):
    real = plant(tmp_path / "bin", "fwtool", tmp_path / "ran.txt")
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    assert same(safe_program.which("fwtool.cmd"), real)
    assert safe_program.which("fwtool.exe") is None


@windows_only
def test_a_system_tool_comes_from_system32_not_the_working_folder(work):
    (work / "taskkill.exe").write_bytes(b"MZ")
    found = safe_program.system_tool("taskkill.exe")
    root = os.environ.get("SystemRoot", "C:\\Windows")
    assert same(found, os.path.join(root, "System32", "taskkill.exe"))


@pytest.mark.skipif(WINDOWS, reason="POSIX reads the PATH handed to the child")
def test_posix_searches_the_path_the_child_gets(work, tmp_path, monkeypatch):
    real = plant(tmp_path / "bin", "fwtool", tmp_path / "ran.txt")
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    assert safe_program.which("fwtool") is None
    assert same(safe_program.which("fwtool", env={"PATH": str(tmp_path / "bin")}), real)
    # A child env without PATH is searched the way subprocess searches it.
    assert safe_program.which("sh", env={"HOME": "/"}) is not None

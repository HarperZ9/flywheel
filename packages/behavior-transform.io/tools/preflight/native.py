"""Windows exe resolver for native command lookup."""

from __future__ import annotations

import os
from pathlib import Path


SHIM_SUFFIXES = {".bat", ".cmd", ".ps1", ".sh"}


def _path_entries(env_path: str | None = None) -> list[Path]:
    raw_path = os.environ.get("PATH", "") if env_path is None else env_path
    return [Path(entry) for entry in raw_path.split(os.pathsep) if entry]


def _is_path_like(command: str) -> bool:
    return any(token in command for token in ("\\", "/", ":"))


def _candidate_exe_from_path(path: Path) -> Path | None:
    if path.suffix.lower() == ".exe" and path.exists():
        return path
    if path.suffix.lower() in SHIM_SUFFIXES:
        exe = path.with_suffix(".exe")
        return exe if exe.exists() else None
    exe = path.with_suffix(".exe") if path.suffix else Path(str(path) + ".exe")
    return exe if exe.exists() else None


def _known_native_exes(command: str) -> list[Path]:
    name = Path(command).stem.lower()
    if name != "codex":
        return []
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return []
    root = Path(local_app_data) / "OpenAI" / "Codex" / "bin"
    if not root.exists():
        return []
    candidates = sorted(root.glob("*/codex.exe"), key=lambda path: path.stat().st_mtime, reverse=True)
    return [path for path in candidates if path.exists()]


def _find_native_exe(command: str, env_path: str | None = None) -> Path | None:
    path = Path(command)
    if _is_path_like(command):
        return _candidate_exe_from_path(path)
    known = _known_native_exes(command)
    if known:
        return known[0]
    names = [command] if Path(command).suffix.lower() == ".exe" else [f"{command}.exe", command]
    for directory in _path_entries(env_path):
        for name in names:
            candidate = directory / name
            if candidate.suffix.lower() == ".exe" and candidate.exists():
                return candidate
    return None


def resolve_native_command(command: list[str], env_path: str | None = None) -> list[str]:
    if not command:
        raise ValueError("child command is required")
    executable = command[0]
    native = _find_native_exe(executable, env_path)
    suffix = Path(executable).suffix.lower()
    if native is None and suffix in SHIM_SUFFIXES:
        raise ValueError(f"native executable not found for shim: {executable}")
    if native is None:
        return command
    return [str(native), *command[1:]]

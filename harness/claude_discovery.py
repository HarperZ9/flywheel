"""Find the claude CLI for articulate's judge, fix and polish (O-14).

articulate 0.5.0 runs the claude CLI in a fresh empty folder with the project
and local settings, every MCP server and every built-in tool turned off, and
reads the CLI's path from ``ARTICULATE_CLAUDE_CLI``. A bundled lane child's
PATH is the system folder, so the engine resolves the CLI itself and passes the
absolute path there (``lane_workdir.forced_env``). The CLI must be signed in
(``claude login``); the engine cannot check that without running a model call,
so the setup item says so instead of claiming it.

Order, first runnable wins, never the current folder:

1. ``ARTICULATE_CLAUDE_CLI`` in the engine's environment, when absolute;
2. ``claude.exe`` in the user PATH, the machine PATH (read from the registry),
   then the engine PATH;
3. ``%USERPROFILE%\\.local\\bin\\claude.exe``, where the native installer puts it;
4. a ``claude.cmd`` shim in those PATH folders or ``%APPDATA%\\npm``, which
   articulate runs under its batch-file argument checks.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

from .tool_discovery import RegistryReader, ToolFinding, _get, _search_places, registry_path

ENV_VAR = "ARTICULATE_CLAUDE_CLI"


def _claude(found: bool, path: str | None, source: str, detail: str) -> ToolFinding:
    return ToolFinding("claude", found, path, None, source, "", detail)


def _candidates(environ: Mapping[str, str], reader: RegistryReader, platform: str):
    folders = [(source, folder) for source, dirs in _search_places(environ, reader, platform)
               for folder in dirs if Path(folder).is_absolute()]
    profile = _get(environ, "USERPROFILE")
    if platform == "nt":
        for source, folder in folders:
            yield source, Path(folder) / "claude.exe"
        if profile:
            yield "user_install", Path(profile) / ".local" / "bin" / "claude.exe"
        appdata = _get(environ, "APPDATA")
        shims = [*folders, *([("npm", str(Path(appdata) / "npm"))] if appdata else [])]
        for source, folder in shims:
            yield source, Path(folder) / "claude.cmd"
    else:
        for source, folder in folders:
            yield source, Path(folder) / "claude"
        if profile or _get(environ, "HOME"):
            yield "user_install", Path(profile or _get(environ, "HOME")) / ".local" / "bin" / "claude"


def find_claude(environ: Mapping[str, str], *,
                read_registry_path: RegistryReader = registry_path,
                platform: str = os.name) -> ToolFinding:
    """The claude CLI, as an absolute path, or why it was not found."""
    pinned = _get(environ, ENV_VAR).strip().strip('"')
    if pinned:
        path = Path(pinned)
        if path.is_absolute() and path.is_file():
            return _claude(True, str(path), ENV_VAR, f"claude at {ENV_VAR}")
        return _claude(False, None, ENV_VAR, f"{ENV_VAR} names no file by an absolute path")
    for source, path in _candidates(environ, read_registry_path, platform):
        if path.is_file():
            return _claude(True, str(path), source, f"claude at {path}")
    return _claude(False, None, "not_found",
                   "no claude CLI found in ARTICULATE_CLAUDE_CLI, PATH or the user install")


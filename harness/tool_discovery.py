"""Find Node and Git for lanes that need a tool the engine does not ship.

The desktop starts the engine with whatever PATH the session had at login, and
the frozen build cuts a lane child's PATH to the system folder. Neither says
where a person installed Node or Git, so discovery reads its own places, in a
fixed order, and never runs anything but ``node --version``.

Node, first usable wins:

1. ``FLYWHEEL_NODE``: a node executable or its folder. ``none`` means not
   found, which is how the acceptance run tests the no-Node state.
2. ``<home>/node_path``: the node executable the person picked in the app,
   with its sha256; a file that no longer matches is not run.
3. The Node the frozen build bundles (``_internal/node-lanes/node``).
4. The user PATH, then the machine PATH, read from the registry (HKCU
   ``Environment``, HKLM ``Session Manager\\Environment``), so a Node installed
   after the engine started is still found.
5. The engine's own PATH.
6. ``%ProgramFiles%\\nodejs\\node.exe``.

A Node older than 20 is skipped when discovered, and reported (not replaced)
when the operator chose it in 1 or 2. Git follows the same shape with
``FLYWHEEL_GIT``, the registry PATH, the engine PATH and
``%ProgramFiles%\\Git\\cmd\\git.exe``, with no version floor.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping

from .lane_workdir import flywheel_home

MIN_NODE_MAJOR = 20
NODE_PATH_FILE = "node_path"
_REG_KEYS = {
    "user": ("HKEY_CURRENT_USER", "Environment"),
    "machine": ("HKEY_LOCAL_MACHINE",
                r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
}
_PERCENT = re.compile(r"%([^%]+)%")
_VERSION = re.compile(r"v?(\d+)\.\d+\.\d+")
RegistryReader = Callable[[str], "str | None"]
VersionProbe = Callable[[str], "str | None"]


@dataclass(frozen=True)
class ToolFinding:
    """Where a tool was found, or why it was not. Holds no secret."""
    tool: str
    found: bool
    path: str | None
    version: str | None
    source: str
    minimum: str
    detail: str

    def to_dict(self) -> dict:
        return asdict(self)


def registry_path(scope: str) -> str | None:
    """The raw ``Path`` value for ``user`` or ``machine`` scope; None when unset."""
    import winreg  # Windows only; callers fall back to the engine PATH elsewhere
    hive_name, key = _REG_KEYS[scope]
    with winreg.OpenKey(getattr(winreg, hive_name), key) as handle:
        try:
            value, _kind = winreg.QueryValueEx(handle, "Path")
        except FileNotFoundError:
            return None
    return value if isinstance(value, str) else None


def expand_env(value: str, environ: Mapping[str, str]) -> str:
    """Expand ``%NAME%`` from ``environ`` (any case); unknown names stay as written."""
    upper = {str(key).upper(): str(val) for key, val in environ.items()}
    return _PERCENT.sub(lambda m: upper.get(m.group(1).upper(), m.group(0)), value)


_VERSIONS: dict[tuple[str, int, int], str] = {}


def _cached_version(path: str, mtime_ns: int, size: int) -> str | None:
    """``--version`` output, cached for a successful answer only, so one slow
    or failed run (an antivirus scan past the timeout) is tried again (C11)."""
    key = (path, mtime_ns, size)
    if key not in _VERSIONS:
        found = _run_version(path)
        if found is None:
            return None
        _VERSIONS[key] = found
    return _VERSIONS[key]


def _run_version(path: str) -> str | None:
    env = {key: value for key, value in os.environ.items()
           if key.upper() in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP"}}
    try:
        result = subprocess.run(
            [path, "--version"], capture_output=True, text=True, timeout=10, env=env,
            creationflags=0x08000000 if os.name == "nt" else 0)  # CREATE_NO_WINDOW
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = result.stdout.strip()
    return text if result.returncode == 0 and node_major(text) is not None else None


def node_version(path: str) -> str | None:
    """``node --version`` for an executable, cached on its size and mtime."""
    try:
        stat = Path(path).stat()
    except OSError:
        return None
    return _cached_version(str(path), stat.st_mtime_ns, stat.st_size)


def file_digest(path: Path) -> str | None:
    """sha256 of a file, read in full on every call; None when unreadable.

    Not cached on size and mtime: a replacement can keep both, and the saved
    Node choice is only a pin if every launch hashes the bytes it will run."""
    try:
        digest = hashlib.sha256()
        with Path(path).open("rb") as handle:
            for block in iter(lambda: handle.read(1 << 20), b""):
                digest.update(block)
        return digest.hexdigest()
    except OSError:
        return None


def node_major(version: str | None) -> int | None:
    match = _VERSION.match(version.strip()) if isinstance(version, str) else None
    return int(match.group(1)) if match else None


def _get(environ: Mapping[str, str], name: str) -> str:
    for key, value in environ.items():
        if isinstance(key, str) and key.upper() == name.upper():
            return str(value)
    return ""


def _exe_name(tool: str, platform: str) -> str:
    return f"{tool}.exe" if platform == "nt" else tool


def _as_exe(value: str, tool: str, platform: str) -> Path | None:
    path = Path(os.path.expanduser(value.strip().strip('"')))
    if path.is_dir():
        path = path / _exe_name(tool, platform)
    return path if path.is_file() else None


def _path_dirs(raw: str | None, environ: Mapping[str, str], platform: str) -> list[str]:
    sep = ";" if platform == "nt" else os.pathsep
    return [part for part in expand_env(raw or "", environ).split(sep) if part.strip()]


def _search_places(environ: Mapping[str, str], reader: RegistryReader,
                   platform: str) -> Iterable[tuple[str, list[str]]]:
    if platform == "nt":
        for scope in ("user", "machine"):
            try:
                raw = reader(scope)
            except (OSError, ImportError, KeyError):
                raw = None
            yield f"{scope}_path", _path_dirs(raw, environ, platform)
    yield "engine_path", _path_dirs(_get(environ, "PATH"), environ, platform)


def _discovered(tool: str, environ, reader, platform, program_files_rel: tuple[str, ...]):
    """Every (source, executable) discovery yields, in order."""
    for source, folders in _search_places(environ, reader, platform):
        for folder in folders:
            exe = _as_exe(folder, tool, platform)
            if exe is not None:
                yield source, exe
    program_files = _get(environ, "PROGRAMFILES")
    if platform == "nt" and program_files:
        exe = Path(program_files).joinpath(*program_files_rel)
        if exe.is_file():
            yield "program_files", exe


def _judge_node(path: Path, source: str, probe: VersionProbe) -> ToolFinding:
    version = probe(str(path))
    major = node_major(version)
    if major is None:
        return _node(False, str(path), None, source, f"{path} did not answer --version")
    if major < MIN_NODE_MAJOR:
        return _node(False, str(path), version, source,
                     f"{path} is Node {version}, older than {MIN_NODE_MAJOR}")
    return _node(True, str(path), version, source, f"Node {version} at {path}")


def _node(found, path, version, source, detail) -> ToolFinding:
    return ToolFinding("node", found, path, version, source, str(MIN_NODE_MAJOR), detail)


def _chosen_node(environ, home) -> tuple[str, str, str | None] | None:
    """The operator's explicit choice: FLYWHEEL_NODE, else ``<home>/node_path``
    (its path and the sha256 saved with it)."""
    pinned = _get(environ, "FLYWHEEL_NODE")
    if pinned:
        return "FLYWHEEL_NODE", pinned, None
    try:
        text = (Path(home) / NODE_PATH_FILE).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    lines = text.splitlines()
    saved = next((line[7:].strip() for line in lines[1:] if line.startswith("sha256=")), "")
    return ("node_path", lines[0], saved) if text else None


def find_node(environ: Mapping[str, str], *, home: Path | None = None,
              bundled: Path | None = None,
              read_registry_path: RegistryReader = registry_path,
              node_version: VersionProbe = node_version,
              platform: str = os.name) -> ToolFinding:
    """Find a Node of at least ``MIN_NODE_MAJOR`` in the documented order."""
    chosen = _chosen_node(environ, flywheel_home(environ) if home is None else home)
    if chosen is not None:
        source, value, saved = chosen
        if value.strip().lower() == "none":
            return _node(False, None, None, "disabled", f"{source}=none")
        exe = _as_exe(value, "node", platform)
        if exe is None:
            return _node(False, None, None, source, f"{source} names no node executable")
        if saved is not None and (not saved or file_digest(exe) != saved):
            return _node(False, str(exe), None, source,
                         "node_path changed since it was chosen; choose node.exe again")
        return _judge_node(exe, source, node_version)
    candidates = [("bundled", Path(bundled))] if bundled and Path(bundled).is_file() else []
    candidates += list(_discovered("node", environ, read_registry_path, platform,
                                   ("nodejs", "node.exe")))
    rejected: list[str] = []
    for source, exe in candidates:
        finding = _judge_node(exe, source, node_version)
        if finding.found:
            return finding
        rejected.append(finding.detail)
    detail = "no Node found in FLYWHEEL_NODE, node_path, the bundled runtime, PATH or Program Files"
    return _node(False, None, None, "not_found", "; ".join([detail, *rejected]))


def find_git(environ: Mapping[str, str], *,
             read_registry_path: RegistryReader = registry_path,
             platform: str = os.name) -> ToolFinding:
    """Find git: FLYWHEEL_GIT, the registry PATH, the engine PATH, Program Files."""
    pinned = _get(environ, "FLYWHEEL_GIT")
    if pinned:
        if pinned.strip().lower() == "none":
            return ToolFinding("git", False, None, None, "disabled", "", "FLYWHEEL_GIT=none")
        exe = _as_exe(pinned, "git", platform)
        return ToolFinding("git", exe is not None, str(exe) if exe else None, None,
                           "FLYWHEEL_GIT", "", "git at FLYWHEEL_GIT" if exe
                           else "FLYWHEEL_GIT names no git executable")
    for source, exe in _discovered("git", environ, read_registry_path, platform,
                                   ("Git", "cmd", "git.exe")):
        return ToolFinding("git", True, str(exe), None, source, "", f"git at {exe}")
    return ToolFinding("git", False, None, None, "not_found", "",
                       "no git found in FLYWHEEL_GIT, PATH or Program Files")

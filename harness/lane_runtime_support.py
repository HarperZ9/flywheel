"""Pure helpers for lane runtime resolution."""
from __future__ import annotations

import functools
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Callable, Mapping

from .lanes_registry import Lane
from .mcp_client import LaunchSpec

UNPROBED_CAPABILITY = {
    "probed": False,
    "tool_count": None,
    "tool_names_sha256": None,
}
_VERSION_RE = re.compile(r"__version__\s*=\s*['\"]([^'\"]+)['\"]")


def resolve_repo(source_repo: str, repo: Path, environ: Mapping[str, str]) -> Path | None:
    source = Path(source_repo)
    if not source_repo:
        return None
    candidates: list[Path] = []
    explicit = environ.get("FLYWHEEL_WORKSPACE_ROOT", "").strip()
    if explicit:
        candidates.append(Path(explicit).expanduser() / source)
    candidates.append(repo.parent / source)
    if source.parts and repo.parent.name == source.parts[0]:
        candidates.append(repo.parent.joinpath(*source.parts[1:]))
    seen: set[Path] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved not in seen and resolved.is_dir():
            return resolved
        seen.add(resolved)
    return None


def resolve_source_repo(lane: Lane, repo: Path, environ: Mapping[str, str]) -> Path | None:
    return resolve_repo(lane.source_repo, repo, environ)


def extra_import_roots(lane: Lane, repo: Path, environ: Mapping[str, str]) -> list[str]:
    roots = []
    for spec in getattr(lane, "extra_source_repos", ()) or ():
        source = resolve_repo(spec, repo, environ)
        if source is None:
            continue
        src = source / "src"
        roots.append(str((src if src.is_dir() else source).resolve()))
    return roots


def importable(top_module: str) -> bool:
    try:
        return importlib.util.find_spec(top_module) is not None
    except (ImportError, ValueError):
        return False


def frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


@functools.lru_cache(maxsize=1)
def _npm_global_root() -> Path | None:
    try:
        npm = "npm.cmd" if os.name == "nt" else "npm"
        result = subprocess.run(
            [npm, "root", "-g"], capture_output=True, text=True, timeout=20,
            creationflags=0x08000000 if os.name == "nt" else 0)  # CREATE_NO_WINDOW
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    line = result.stdout.strip()
    return Path(line) if line else None


def installed_version(lane: Lane) -> str | None:
    try:
        if lane.kind == "bundled":
            return lane.version
        if lane.kind == "pip":
            try:
                return importlib.metadata.version(lane.install_name)
            except importlib.metadata.PackageNotFoundError:
                return None
        if lane.kind == "npm":
            root = _npm_global_root()
            if root is None:
                return None
            try:
                data = json.loads(
                    (root / lane.install_name / "package.json").read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None
            version = data.get("version")
            return version if isinstance(version, str) else None
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return None
    return None


def package_runtime_version(lane: Lane, python_executable: str) -> str | None:
    if lane.kind != "pip" or not lane.install_name:
        return None
    code = (
        "import importlib.metadata, sys\n"
        "try:\n"
        " print(importlib.metadata.version(sys.argv[1]))\n"
        "except importlib.metadata.PackageNotFoundError:\n"
        " raise SystemExit(2)\n"
    )
    try:
        result = subprocess.run(
            [python_executable, "-I", "-c", code, lane.install_name],
            capture_output=True, text=True, timeout=8,
            creationflags=0x08000000 if os.name == "nt" else 0)  # CREATE_NO_WINDOW
    except (FileNotFoundError, PermissionError, subprocess.TimeoutExpired, OSError):
        return None
    version = result.stdout.strip()
    return version if result.returncode == 0 and version else None


def python_import_root(source: Path, lane: Lane) -> Path:
    top = lane.py_module.split(".", 1)[0]
    for root in (source / "src", source):
        if (root / top).is_dir() or (root / f"{top}.py").is_file():
            return root.resolve()
    return source.resolve()


def pip_mcp_command(lane: Lane, python_executable: str,
                    importable_fn: Callable[[str], bool]) -> list[str]:
    if lane.py_module:
        top = lane.py_module.split(".", 1)[0]
        if importable_fn(top):
            return [python_executable, "-m", lane.py_module, *lane.mcp_args]
    return lane.mcp_command()


def source_launch(lane: Lane, source: Path, python_executable: str,
                  environ: Mapping[str, str],
                  extra_roots: Callable[[Lane], list[str]]) -> LaunchSpec:
    if lane.kind == "npm":
        return LaunchSpec(("node", str((source / lane.mcp_args[0]).resolve())))
    if lane.kind == "pip" and lane.py_module:
        roots = [str(python_import_root(source, lane)), *extra_roots(lane)]
        inherited = environ.get("PYTHONPATH", "")
        if inherited:
            roots.append(inherited)
        return LaunchSpec(
            (python_executable, "-m", lane.py_module, *lane.mcp_args),
            str(source.resolve()),
            (("PYTHONPATH", os.pathsep.join(roots)), ("PYTHONSAFEPATH", "1")),
        )
    return LaunchSpec(tuple(lane.mcp_command()))


def package_launch(lane: Lane, python_executable: str,
                   importable_fn: Callable[[str], bool],
                   runtime_python: str | None) -> LaunchSpec:
    if lane.kind == "pip":
        if runtime_python and lane.py_module:
            return LaunchSpec(
                (runtime_python, "-I", "-m", lane.py_module, *lane.mcp_args))
        return LaunchSpec(tuple(pip_mcp_command(lane, python_executable, importable_fn)))
    return LaunchSpec(tuple(lane.mcp_command()))


def source_runtime_version(lane: Lane, source: Path) -> str | None:
    if lane.kind == "npm":
        return _json_version(source / "package.json")
    if lane.kind != "pip":
        return None
    version = _pyproject_version(source / "pyproject.toml")
    if version:
        return version
    root = python_import_root(source, lane)
    top = lane.py_module.split(".", 1)[0]
    try:
        match = _VERSION_RE.search((root / top / "__init__.py").read_text(encoding="utf-8"))
    except OSError:
        return None
    return match.group(1) if match else None


def capability_summary(tools: list) -> dict:
    names = sorted(t.get("name", "") for t in tools
                   if isinstance(t, dict) and isinstance(t.get("name"), str))
    digest = hashlib.sha256(
        json.dumps(names, separators=(",", ":")).encode()).hexdigest()
    return {"probed": True, "tool_count": len(names), "tool_names_sha256": digest}


def launch_summary(launch: LaunchSpec | None) -> dict:
    if launch is None:
        return {"argv_shape": [], "cwd_selected": False, "env_override_keys": []}
    return {
        "argv_shape": [_safe_arg(arg, index) for index, arg in enumerate(launch.argv)],
        "cwd_selected": bool(launch.cwd),
        "env_override_keys": sorted(key for key, _ in launch.env_overrides),
        "inherit_env": launch.inherit_env,
        "url_selected": bool(launch.url),
    }


def _pyproject_version(path: Path) -> str | None:
    try:
        import tomllib
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, ModuleNotFoundError):
        return None
    version = data.get("project", {}).get("version")
    return version if isinstance(version, str) else None


def _json_version(path: Path) -> str | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    version = data.get("version")
    return version if isinstance(version, str) else None


def _safe_arg(value: str, index: int) -> str:
    name = _basename(value)
    if index == 0 and name.lower().startswith("python"):
        return "python"
    if index == 0 and name.lower().startswith("node"):
        return "node"
    if index == 0 and name != value:
        return "executable"
    return name if name != value else value


def _basename(value: str) -> str:
    if "\\" in value or (len(value) > 2 and value[1] == ":"):
        return PureWindowsPath(value).name
    if "/" in value:
        return PurePosixPath(value).name
    return value

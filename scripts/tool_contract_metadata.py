"""Metadata-only entrypoint inspection for tool contract reports."""

from __future__ import annotations

import hashlib
import re
import tomllib
from pathlib import Path
from typing import Any


MAX_PYPROJECT_BYTES = 262_144
DECLARED_CLI_LIMIT = "metadata declaration only; not installed or exercised"
UNVERIFIED_PROFILE_LIMIT = "unverified fallback profile; metadata absent, empty, invalid, unsafe, too large, or unsupported"
PYPROJECT_SCOPE = "reads only selected_root/pyproject.toml [project.scripts] when it is a regular file under the selected root; no imports, subprocesses, endpoints, or target-path reads"
SCRIPT_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
PYTHON_ENTRYPOINT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*:[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")


def _source(status: str, sha256: str | None) -> dict[str, Any]:
    return {"filename": "pyproject.toml", "sha256": sha256, "status": status}


def _inside(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _pyproject_file(root: Path) -> tuple[Path | None, str]:
    path = root / "pyproject.toml"
    if not root.exists():
        return None, "root_missing"
    if not path.exists():
        return None, "absent"
    try:
        root_real = root.resolve(strict=True)
        path_real = path.resolve(strict=True)
    except OSError:
        return None, "unsafe_path"
    if path.is_symlink() or not _inside(path_real, root_real):
        return None, "unsafe_path"
    if not path.is_file():
        return None, "invalid"
    try:
        if path.stat().st_size > MAX_PYPROJECT_BYTES:
            return None, "too_large"
    except OSError:
        return None, "invalid"
    return path, "readable"


def _supported_script(name: str, target: str) -> bool:
    return bool(SCRIPT_NAME_RE.fullmatch(name) and PYTHON_ENTRYPOINT_RE.fullmatch(target))


def project_scripts_metadata(root: Path) -> dict[str, Any]:
    """Return sanitized PEP 621 script declarations from one selected root."""
    path, path_status = _pyproject_file(root)
    if path is None:
        return {"status": path_status, "source": _source(path_status, None), "declarations": []}
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_PYPROJECT_BYTES + 1)
        if len(raw) > MAX_PYPROJECT_BYTES:
            return {"status": "too_large", "source": _source("too_large", None), "declarations": []}
        sha256 = hashlib.sha256(raw).hexdigest()
    except OSError:
        return {"status": "invalid", "source": _source("invalid", None), "declarations": []}
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError):
        return {"status": "invalid", "source": _source("invalid", sha256), "declarations": []}
    if "project" not in data:
        return {"status": "absent", "source": _source("absent", sha256), "declarations": []}
    project = data["project"]
    if not isinstance(project, dict):
        return {"status": "invalid", "source": _source("invalid", sha256), "declarations": []}
    scripts = project.get("scripts")
    if scripts is None:
        return {"status": "absent", "source": _source("absent", sha256), "declarations": []}
    if not isinstance(scripts, dict):
        return {"status": "invalid", "source": _source("invalid", sha256), "declarations": []}
    declarations = []
    for name, target in sorted(scripts.items()):
        if not isinstance(name, str) or not isinstance(target, str):
            return {"status": "invalid", "source": _source("invalid", sha256), "declarations": []}
        if not _supported_script(name, target):
            return {"status": "unsupported", "source": _source("unsupported", sha256), "declarations": []}
        declarations.append({"name": name, "target": target, "declaration": f"{name} = {target}"})
    status = "declared" if declarations else "empty"
    return {"status": status, "source": _source(status, sha256), "declarations": declarations}


def cli_entrypoint_view(root: Path, profile_cli: list[str]) -> tuple[list[str], dict[str, Any]]:
    scripts = project_scripts_metadata(root)
    declared = scripts["status"] == "declared"
    fallback_status = "not_used" if declared else "unverified_profile"
    return (
        [item["name"] for item in scripts["declarations"]] if declared else list(profile_cli),
        {
            "scope": PYPROJECT_SCOPE,
            "cli_source": "pyproject_project_scripts" if declared else "unverified_profile",
            "cli_limit": DECLARED_CLI_LIMIT if declared else UNVERIFIED_PROFILE_LIMIT,
            "project_scripts": scripts,
            "fallback_profile": {
                "status": fallback_status,
                "cli": list(profile_cli),
                "limit": UNVERIFIED_PROFILE_LIMIT if fallback_status == "unverified_profile" else "",
            },
        },
    )

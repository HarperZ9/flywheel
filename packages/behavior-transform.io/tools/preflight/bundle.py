"""Export with exclusion filtering."""

from __future__ import annotations

import json
from pathlib import Path
import shutil


EXCLUDED_PARTS = {
    ".warden-prefire",
    ".warden-safe-cache",
    "__pycache__",
    ".pytest_cache",
    "bin",
    "build",
    "dist",
    "obj",
    "bundles",
    "installers",
    "tests",
}

EXCLUDED_SUBSTRINGS = (
    "raw-audit",
    "access-runbook",
    "implementation-plan",
    "primitive-design",
)


def should_exclude(path: Path) -> bool:
    parts = path.parts
    name = path.name.lower()
    lower_path = str(path).lower()
    if name == ".env" or name.startswith(".env."):
        return True
    if any(part in EXCLUDED_PARTS for part in parts):
        return True
    return any(token in lower_path for token in EXCLUDED_SUBSTRINGS)


def export_bundle(source: Path, dest: Path, force: bool = False) -> Path:
    target = dest / "warden-prefire"
    if target.exists():
        if not force:
            raise FileExistsError(f"bundle target exists: {target}")
        shutil.rmtree(target)

    entries = list(source.rglob("*"))
    target.mkdir(parents=True, exist_ok=True)
    for item in entries:
        relative = item.relative_to(source)
        if should_exclude(relative):
            continue
        destination = target / relative
        if item.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, destination)
    _vendor_manifest_tools(target)
    return target


def _tool_paths_from_surface(surface: dict) -> list[Path]:
    paths: list[Path] = []
    io_channel = surface.get("io_channel")
    if isinstance(io_channel, str):
        paths.append(Path(io_channel))
    for raw_path in surface.get("required_paths", []):
        if isinstance(raw_path, str):
            paths.append(Path(raw_path))
    return paths


def _vendor_manifest_tools(target: Path) -> None:
    manifest_path = target / "config" / "surface-manifest.json"
    if not manifest_path.exists():
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    tools_dir = target / "tools"
    copied: dict[str, str] = {}
    for surface in manifest.get("surfaces", {}).values():
        for source_path in _tool_paths_from_surface(surface):
            if not source_path.is_file():
                continue
            destination = tools_dir / source_path.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            if source_path.resolve() != destination.resolve():
                shutil.copy2(source_path, destination)
            copied[str(source_path)] = f"tools/{source_path.name}"

    for surface in manifest.get("surfaces", {}).values():
        io_channel = surface.get("io_channel")
        if isinstance(io_channel, str):
            surface["io_channel"] = copied.get(io_channel, io_channel)
        surface["required_paths"] = [
            copied.get(raw_path, raw_path)
            for raw_path in surface.get("required_paths", [])
            if isinstance(raw_path, str)
        ]
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

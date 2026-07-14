"""projects.py -- the projects registry: directories the surface knows.

A project is {name, root, kind}. Registering a directory makes it a
first-class target for indexing, planning, workspace-scoped agents, and the
knowledge graph. The registry persists under ~/.flywheel/projects.json
(FLYWHEEL_HOME honored). A root must be an existing directory; a missing one
is refused by name, never silently kept. Registration stores a path only --
nothing is read or indexed until a view explicitly asks."""
from __future__ import annotations

import json
import os
from pathlib import Path


def _registry_path() -> Path:
    home = os.environ.get("FLYWHEEL_HOME") or os.path.join(
        os.path.expanduser("~"), ".flywheel")
    return Path(home) / "projects.json"


def _load() -> list:
    p = _registry_path()
    if not p.exists():
        return []
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
        entries = doc.get("projects", [])
        return entries if isinstance(entries, list) else []
    except (OSError, ValueError):
        return []


def _save(entries: list) -> None:
    p = _registry_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"schema": "flywheel.projects/v1",
                             "projects": entries}, indent=1),
                 encoding="utf-8")


def _infer_kind(root: Path) -> str:
    """A cheap, honest kind guess from marker files; 'unknown' when unsure."""
    markers = {
        "pubspec.yaml": "flutter", "Cargo.toml": "rust",
        "package.json": "node", "pyproject.toml": "python",
        "go.mod": "go", "pom.xml": "java", "CMakeLists.txt": "cmake",
    }
    for marker, kind in markers.items():
        if (root / marker).is_file():
            return kind
    # A directory of many repos reads as a monorepo/workspace.
    subrepos = sum(1 for c in root.iterdir()
                   if c.is_dir() and (c / ".git").exists()) \
        if root.is_dir() else 0
    if subrepos >= 2:
        return "monorepo"
    return "unknown"


def project_roster() -> dict:
    """Every registered project, with a live existence check."""
    out = []
    for e in _load():
        root = Path(e.get("root", ""))
        out.append({"name": e.get("name", ""), "root": str(root),
                    "kind": e.get("kind", "unknown"),
                    "exists": root.is_dir()})
    return {"schema": "flywheel.projects/v1", "projects": out, "n": len(out)}


def add_project(root: str, name: str = "") -> dict:
    raw = (root or "").strip()
    if not raw:
        return {"error": "provide a project 'root'"}
    try:
        p = Path(raw).expanduser().resolve()
    except (OSError, ValueError) as e:
        return {"error": f"invalid root: {e}"}
    if not p.is_dir():
        return {"error": f"root is not an existing directory: {raw}"}
    name = (name or p.name).strip()
    entries = _load()
    if any(e.get("root") == str(p) for e in entries):
        return {"error": f"already registered: {p}"}
    entries.append({"name": name, "root": str(p), "kind": _infer_kind(p)})
    _save(entries)
    return {"added": name, "root": str(p), "n": len(entries)}


def remove_project(root: str) -> dict:
    try:
        target = str(Path((root or "").strip()).expanduser().resolve())
    except (OSError, ValueError):
        target = (root or "").strip()
    entries = _load()
    kept = [e for e in entries if e.get("root") != target]
    if len(kept) == len(entries):
        return {"error": f"no registered project at: {root}"}
    _save(kept)
    return {"removed": target, "n": len(kept)}

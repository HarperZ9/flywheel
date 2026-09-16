"""Build the source-basis manifest for packaging the Studio body runtime."""

from __future__ import annotations

import ast
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from harness.studio_body_engine_render import ACCEPTED_ENGINE_HEAD
from harness.studio_body_engine_resolution import (
    REQUIRED_STUDIO_ENGINE_FILES,
    StudioEngineUnavailable,
    resolve_studio_engine_runtime,
    studio_engine_runtime_manifest,
)

SCHEMA = "flywheel.studio-body-runtime-manifest/v1"
ACCOUNTABLE_SURFACE_ENTRY_MODULES = (
    "accountable_surface.api_effector",
    "accountable_surface.authority_store",
    "accountable_surface.effector",
    "accountable_surface.read_authority",
    "accountable_surface.registry",
    "accountable_surface.remote_actuation",
    "accountable_surface.surface",
)
COHERENCE_MEMBRANE_ENTRY_MODULES = (
    "coherence_membrane.membrane",
    "coherence_membrane.observation",
    "coherence_membrane.organs.web",
)
PROOF_SURFACE_ENTRY_MODULES = ("proof_surface",)


def build_studio_body_runtime_manifest(
    *,
    studio_engine_src: Path | str | None,
    accountable_surface_src: Path | str | None,
    coherence_membrane_src: Path | str | None,
    proof_surface_src: Path | str | None,
    created_at: str | None = None,
) -> dict[str, Any]:
    manifest = {
        "schema": SCHEMA,
        "created_at": created_at or datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "studio_engine": _engine_section(studio_engine_src),
        "accountable_surface": _package_section(
            accountable_surface_src, "accountable_surface", ACCOUNTABLE_SURFACE_ENTRY_MODULES),
        "coherence_membrane": _package_section(
            coherence_membrane_src, "coherence_membrane", COHERENCE_MEMBRANE_ENTRY_MODULES),
        "proof_surface": _package_section(
            proof_surface_src, "proof_surface", PROOF_SURFACE_ENTRY_MODULES),
        "packaging_actions": [
            {
                "action": "install_studio_engine_wheel",
                "source": "accepted studio-engine distribution",
                "destination": "frozen Python site-packages",
                "note": "Requires studio_engine/ plus studio_engine-*.dist-info metadata; no root pyproject.toml is expected.",
            },
            {
                "action": "copy_studio_engine_runtime",
                "source": "studio_engine.required_files",
                "destination": "harness/studio_engine_bundle/",
                "note": "Alternative bundled source-style layout; preserve root pyproject.toml and relative paths.",
            },
            {
                "action": "bundle_accountable_surface_stack",
                "source": "accountable_surface/coherence_membrane/proof_surface file closures",
                "destination": "packaged Python runtime or installer payload",
                "note": "Do not load these from private reviewer worktrees in a shipped build.",
            },
        ],
        "release_boundary": [
            "STUDIO_ENGINE_SRC may be used for accepted-source tests and local review.",
            "Shipped native builds must resolve an installed package or bundled runtime.",
            "A missing external runtime is unavailable, not a fake engine.",
        ],
    }
    _expand_cross_package_dependencies(manifest)
    return manifest


def _expand_cross_package_dependencies(manifest: dict[str, Any]) -> None:
    sections = {name: section for name, section in manifest.items()
                if isinstance(section, dict) and section.get("source_root")
                and section.get("status") == "ready"}
    changed = True
    while changed:
        changed = False
        for source_name, source in sections.items():
            source_root = Path(source["source_root"])
            for target_name, target in sections.items():
                if source_name == target_name:
                    continue
                root = Path(target["source_root"])
                entries: set[str] = set()
                for rel in source["files"]:
                    module = rel.removesuffix(".py").replace("/", ".")
                    entries.update(_imports_for(root, target_name, module, source_root / rel))
                files = set(target["files"]) | set(_module_closure(root, target_name, entries))
                if files != set(target["files"]):
                    target["files"] = sorted(files)
                    target["file_hashes"] = {rel: _sha256(root / rel) for rel in sorted(files)}
                    changed = True


def _engine_section(source: Path | str | None) -> dict[str, Any]:
    if source is None:
        return {"status": "unconfigured", "expected_head": ACCEPTED_ENGINE_HEAD,
                "required_files": list(REQUIRED_STUDIO_ENGINE_FILES)}
    try:
        runtime = resolve_studio_engine_runtime(
            env={"STUDIO_ENGINE_SRC": str(source)}, bundled_roots=(), installed_roots=())
    except StudioEngineUnavailable as exc:
        return {"status": "unavailable", "code": exc.code, "reason": str(exc),
                "expected_head": ACCEPTED_ENGINE_HEAD,
                "required_files": list(REQUIRED_STUDIO_ENGINE_FILES)}
    out = studio_engine_runtime_manifest(runtime)
    out.update({"status": "ready", "expected_head": ACCEPTED_ENGINE_HEAD})
    return out


def _package_section(
    source: Path | str | None,
    package: str,
    entries: Iterable[str],
) -> dict[str, Any]:
    if source is None:
        return {"status": "unconfigured", "entry_modules": list(entries), "files": []}
    root = Path(source).expanduser().resolve()
    if not root.exists():
        return {"status": "unavailable", "reason": f"{package} source root is absent",
                "entry_modules": list(entries), "files": []}
    files = _module_closure(root, package, entries)
    return {
        "status": "ready",
        "source_root": str(root),
        "entry_modules": list(entries),
        "files": files,
        "file_hashes": {rel: _sha256(root / rel) for rel in files},
    }


def _module_closure(root: Path, package: str, entries: Iterable[str]) -> list[str]:
    pending = set(entries)
    seen: set[str] = set()
    files: set[str] = set()
    while pending:
        module = pending.pop()
        if module in seen or not module.startswith(package):
            continue
        seen.add(module)
        path = _module_path(root, module)
        if path is None:
            continue
        rel = path.relative_to(root).as_posix()
        files.add(rel)
        pending.update(_imports_for(root, package, module, path))
    return sorted(files)


def _module_path(root: Path, module: str) -> Path | None:
    parts = module.split(".")
    direct = root.joinpath(*parts).with_suffix(".py")
    package_init = root.joinpath(*parts, "__init__.py")
    if direct.is_file():
        return direct
    if package_init.is_file():
        return package_init
    return None


def _imports_for(root: Path, package: str, module: str, path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return set()
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            found.update(_from_import_modules(root, package, module, node))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(package + "."):
                    found.add(alias.name)
    return found


def _from_import_modules(root: Path, package: str, module: str, node: ast.ImportFrom) -> set[str]:
    base = _import_base(module, node.level, node.module)
    if base is None or not base.startswith(package):
        return set()
    found = {base}
    for alias in node.names:
        if alias.name == "*":
            continue
        candidate = base + "." + alias.name
        if _module_path(root, candidate) is not None:
            found.add(candidate)
    return found


def _import_base(module: str, level: int, imported: str | None) -> str | None:
    if level == 0:
        return imported
    module_parts = module.split(".")
    keep = max(1, len(module_parts) - level)
    parts = module_parts[:keep]
    if imported:
        parts.extend(imported.split("."))
    return ".".join(parts) if parts else imported


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

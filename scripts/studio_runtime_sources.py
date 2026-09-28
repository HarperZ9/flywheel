"""Pinned source inputs for reproducible Studio runtime payload staging."""

from __future__ import annotations

import copy
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Mapping

from scripts.studio_runtime_manifest import (
    MANIFEST_SCHEMA,
    PACKAGE_SECTIONS,
    relative_files,
    section_rows,
    validate_entry_modules,
    validate_manifest_sources,
)

SOURCE_PINS_SCHEMA = "flywheel.studio-runtime-sources/v1"
COMPONENTS = ("studio_engine", *PACKAGE_SECTIONS)
COMPONENT_KEYS = {"repo", "ref", "source_subdir", "license_notices", "manifest"}
COMMIT_REF = re.compile(r"^[0-9a-f]{40}$")


def load_source_pins(path: Path | str) -> dict[str, Any]:
    source = Path(path)
    if not source.is_file():
        raise RuntimeError(f"Studio runtime source pins are missing: {source}")
    try:
        doc = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError("Studio runtime source pins are not valid JSON") from exc
    _validate_source_pins(doc)
    return doc


def build_manifest_from_source_pins(
    pins: Mapping[str, Any],
    *,
    checkout_roots: Mapping[str, Path | str],
) -> tuple[dict[str, Any], list[Path]]:
    components = pins["components"]
    manifest: dict[str, Any] = {
        "schema": MANIFEST_SCHEMA,
        "created_at": pins.get("created_at"),
    }
    notices: list[Path] = []
    for name in COMPONENTS:
        root = Path(checkout_roots[name]).resolve()
        component = components[name]
        section = copy.deepcopy(component["manifest"])
        source_subdir = component["source_subdir"]
        source_root = (root / source_subdir).resolve() if source_subdir else root
        try:
            source_root.relative_to(root)
        except ValueError as exc:
            raise RuntimeError(f"{name} source_subdir escaped checkout root") from exc
        if name == "studio_engine":
            section["root"] = str(source_root)
        else:
            section["source_root"] = str(source_root)
        manifest[name] = section
        notices.extend(root / rel for rel in component["license_notices"])
    validate_manifest_sources(manifest)
    return manifest, notices


def checkout_source_pins(
    pins: Mapping[str, Any],
    *,
    work_root: Path | str,
    git: str = "git",
) -> dict[str, Path]:
    root = Path(work_root)
    if root.exists() and any(root.iterdir()):
        raise RuntimeError("Studio runtime source checkout root must be empty")
    root.mkdir(parents=True, exist_ok=True)
    checkouts = {}
    for name in COMPONENTS:
        component = pins["components"][name]
        destination = root / name
        _run([git, "clone", "--config", "core.autocrlf=false",
              "--no-tags", "--filter=blob:none",
              component["repo"], str(destination)])
        _run([git, "-C", str(destination), "checkout", "--detach", component["ref"]])
        head = subprocess.check_output(
            [git, "-C", str(destination), "rev-parse", "HEAD"], text=True).strip()
        if head != component["ref"]:
            raise RuntimeError(f"{name} checkout did not reach pinned ref")
        checkouts[name] = destination
    return checkouts


def _validate_source_pins(doc: Any) -> None:
    if not isinstance(doc, dict) or doc.get("schema") != SOURCE_PINS_SCHEMA:
        raise RuntimeError("Studio runtime source pins schema mismatch")
    if set(doc) - {"schema", "created_at", "components"}:
        raise RuntimeError("unsupported Studio runtime source pins field")
    components = doc.get("components")
    if not isinstance(components, dict) or set(components) != set(COMPONENTS):
        raise RuntimeError("Studio runtime source pins must name all components")
    for name in COMPONENTS:
        _validate_component(name, components[name])


def _validate_component(name: str, component: Any) -> None:
    if not isinstance(component, dict) or set(component) != COMPONENT_KEYS:
        raise RuntimeError(f"{name} source pin keys are invalid")
    repo = component["repo"]
    if not isinstance(repo, str) or not repo.startswith("https://"):
        raise RuntimeError(f"{name} repo must be a public https URL")
    if "C:/dev" in repo or "\\" in repo or any(ord(ch) < 32 for ch in repo):
        raise RuntimeError(f"{name} repo must be a public https URL")
    ref = component["ref"]
    if not isinstance(ref, str) or COMMIT_REF.fullmatch(ref) is None:
        raise RuntimeError(f"{name} ref must be a 40-hex commit")
    subdir = component["source_subdir"]
    if not isinstance(subdir, str):
        raise RuntimeError(f"{name} source_subdir must be a string")
    if subdir:
        relative_files([subdir], f"{name}.source_subdir")
    relative_files(component["license_notices"], f"{name}.license_notices")
    section = component["manifest"]
    if name == "studio_engine":
        section_rows({"studio_engine": section}, name, require_source=False)
    else:
        rows = section_rows({name: section}, name, require_source=False)
        validate_entry_modules(section, {rel.as_posix() for _, _, rel in rows})


def _run(command: list[str]) -> None:
    subprocess.run(command, check=True)

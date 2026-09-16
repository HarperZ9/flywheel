"""Portable Studio Engine runtime resolution for the Studio body bridge."""

from __future__ import annotations

import hashlib
import importlib.metadata
import os
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

RUNTIME_RESOLUTION_SCHEMA = "flywheel.studio-engine-runtime-resolution/v1"
STUDIO_ENGINE_SRC_ENV = "STUDIO_ENGINE_SRC"
STUDIO_ENGINE_DISTRIBUTION = "studio-engine"

REQUIRED_STUDIO_ENGINE_SOURCE_FILES = (
    "pyproject.toml",
    "studio_engine/__init__.py",
    "studio_engine/engine.py",
    "studio_engine/model.py",
    "studio_engine/certify.py",
    "studio_engine/corpus.py",
    "studio_engine/criteria.py",
    "studio_engine/registry.py",
    "studio_engine/temporal.py",
    "studio_engine/raster_renderer.py",
    "studio_engine/organs/__init__.py",
    "studio_engine/organs/attractor.py",
    "studio_engine/organs/fields.py",
    "studio_engine/organs/flowfield.py",
    "studio_engine/organs/geometry.py",
    "studio_engine/organs/harmonograph.py",
    "studio_engine/organs/metaballs.py",
    "studio_engine/organs/moire.py",
    "studio_engine/organs/palette.py",
    "studio_engine/organs/program.py",
    "studio_engine/organs/raster.py",
    "studio_engine/organs/rings.py",
    "studio_engine/organs/sonify.py",
    "studio_engine/organs/turbulence.py",
    "studio_engine/strand/__init__.py",
    "studio_engine/strand/expr.py",
    "studio_engine/strand/glsl.py",
    "studio_engine/strand/recipe.py",
    "studio_engine/strand/webaudio.py",
)
REQUIRED_STUDIO_ENGINE_INSTALLED_FILES = tuple(
    rel for rel in REQUIRED_STUDIO_ENGINE_SOURCE_FILES if rel != "pyproject.toml"
)
REQUIRED_STUDIO_ENGINE_FILES = REQUIRED_STUDIO_ENGINE_SOURCE_FILES
_NAME_SEPARATORS = re.compile(r"[-_.]+")


@dataclass(frozen=True)
class StudioEngineRuntime:
    root: Path
    basis: str
    package_version: str | None = None
    distribution_name: str | None = None
    required_files: tuple[str, ...] = REQUIRED_STUDIO_ENGINE_SOURCE_FILES


class StudioEngineUnavailable(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def resolve_studio_engine_runtime(
    *,
    env: Mapping[str, str] | None = None,
    bundled_roots: Iterable[Path | str] | None = None,
    installed_roots: Iterable[Path | str] | None = None,
) -> StudioEngineRuntime:
    source_env = os.environ if env is None else env
    override = source_env.get(STUDIO_ENGINE_SRC_ENV)
    if override:
        root = _validate_source_root(Path(override), "env:" + STUDIO_ENGINE_SRC_ENV)
        return StudioEngineRuntime(
            root, "env:" + STUDIO_ENGINE_SRC_ENV,
            required_files=REQUIRED_STUDIO_ENGINE_SOURCE_FILES)

    for candidate in _default_bundled_roots() if bundled_roots is None else bundled_roots:
        path = Path(candidate)
        if path.exists():
            return StudioEngineRuntime(
                _validate_source_root(path, "bundled"), "bundled",
                required_files=REQUIRED_STUDIO_ENGINE_SOURCE_FILES)

    installed = _default_installed_roots() if installed_roots is None else (
        (Path(root), None, None) for root in installed_roots)
    for candidate, version, distribution_name in installed:
        path = Path(candidate)
        if path.exists():
            return StudioEngineRuntime(
                _validate_installed_root(path, _installed_basis(distribution_name)),
                _installed_basis(distribution_name), package_version=version,
                distribution_name=distribution_name,
                required_files=REQUIRED_STUDIO_ENGINE_INSTALLED_FILES)

    raise StudioEngineUnavailable(
        "studio_engine_unavailable",
        "Studio Engine runtime unavailable; set STUDIO_ENGINE_SRC or install/bundle studio-engine",
    )


def studio_engine_runtime_manifest(runtime: StudioEngineRuntime) -> dict:
    return {
        "schema": RUNTIME_RESOLUTION_SCHEMA,
        "basis": runtime.basis,
        "root": str(runtime.root),
        "package_version": runtime.package_version,
        "distribution_name": runtime.distribution_name,
        "required_files": list(runtime.required_files),
        "required_file_hashes": {rel: _sha256(runtime.root / rel) for rel in runtime.required_files},
    }


def _validate_source_root(root: Path, basis: str) -> Path:
    resolved = root.expanduser().resolve()
    missing = _missing(resolved, REQUIRED_STUDIO_ENGINE_SOURCE_FILES)
    if missing:
        raise StudioEngineUnavailable(
            "studio_engine_incomplete",
            "missing required Studio Engine runtime file for "
            f"{basis}: {missing[0]}",
        )
    if _normalized_project_name(_pyproject_name(resolved)) != STUDIO_ENGINE_DISTRIBUTION:
        raise StudioEngineUnavailable(
            "studio_engine_identity_mismatch",
            "Studio Engine runtime pyproject.toml does not identify studio-engine",
        )
    return resolved


def _validate_installed_root(root: Path, basis: str) -> Path:
    resolved = root.expanduser().resolve()
    missing = _missing(resolved, REQUIRED_STUDIO_ENGINE_INSTALLED_FILES)
    if missing:
        raise StudioEngineUnavailable(
            "studio_engine_incomplete",
            "missing required Studio Engine runtime file for "
            f"{basis}: {missing[0]}",
        )
    return resolved


def _pyproject_name(root: Path) -> str:
    try:
        data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise StudioEngineUnavailable(
            "studio_engine_identity_mismatch",
            "Studio Engine runtime pyproject.toml cannot be parsed",
        ) from exc
    project = data.get("project")
    if not isinstance(project, dict) or not isinstance(project.get("name"), str):
        raise StudioEngineUnavailable(
            "studio_engine_identity_mismatch",
            "Studio Engine runtime pyproject.toml has no project.name",
        )
    return project["name"]


def _default_bundled_roots() -> tuple[Path, ...]:
    package_root = Path(__file__).resolve().parent
    return (
        package_root / "studio_engine_bundle",
        Path(sys.prefix) / "share" / "flywheel" / "studio-engine",
    )


def _default_installed_roots() -> tuple[tuple[Path, str | None, str], ...]:
    try:
        dist = importlib.metadata.distribution(STUDIO_ENGINE_DISTRIBUTION)
    except importlib.metadata.PackageNotFoundError:
        return ()
    name = dist.metadata.get("Name", "")
    if _normalized_project_name(name) != STUDIO_ENGINE_DISTRIBUTION:
        return ()
    return ((Path(dist.locate_file("")), dist.version, name),)


def _installed_basis(distribution_name: str | None) -> str:
    if distribution_name:
        return "installed:" + _normalized_project_name(distribution_name)
    return "installed:explicit-root"


def _normalized_project_name(value: str | None) -> str:
    return _NAME_SEPARATORS.sub("-", (value or "").strip()).lower()


def _missing(root: Path, files: Iterable[str]) -> list[str]:
    return [rel for rel in files if not (root / rel).is_file()]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

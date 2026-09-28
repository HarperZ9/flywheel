"""Row assembly for the Python-lane payload generator.

Builds the ``owner_project`` block and the full payload row. Git/source
primitives live in ``_lane_payload_source.py``, the MCP surface reader in
``_lane_payload_mcp.py``, reviewed slices in ``_lane_payload_slice.py`` and the
Studio dependency path in ``_lane_payload_studio.py``; the CLI entrypoint is
``generate_python_lane_payload_row.py``.

The admitted tools come from ``harness.lane_tool_policy``: the row admits the
policy's T1 tools that are in the build, and every one must be a tool the lane
serves.
"""
from __future__ import annotations

import shutil
import sys
import tomllib
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
for _p in (str(_ROOT), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from harness.lane_tool_policy import admitted_tools
from harness.lanes_registry import LANES
from _lane_payload_mcp import mcp_block
from _lane_payload_slice import (
    check_slice_closure,
    requirement_import_name,
    slice_for,
    slice_paths,
    split_runtime_dependencies,
)
from _lane_payload_source import (
    COMPONENT_SCHEMA,
    DOES_NOT_PROVE,
    PACKAGING_BOUNDARY,
    ROW_SCHEMA,
    GeneratorError,
    _blob_bytes,
    _digest,
    _filtered_bytes,
    _find_package_dir,
    _git,
    _hash_bytes,
    _hidden_imports,
    _nearest_tag,
    _package_blobs,
    _source_block,
    _tracked_paths,
    _version_from_init,
)
from _lane_payload_studio import studio_dependency_root


def _license_value(project: dict[str, Any]) -> str | dict[str, str]:
    """The declared license as written: an SPDX string or a ``{text = ...}`` table."""
    value = project.get("license")
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and isinstance(value.get("text"), str):
        return {"text": value["text"]}
    raise GeneratorError("project.license is not a plain SPDX/string expression")


def _license_files(
    checkout: Path, rev: str, project: dict[str, Any]
) -> list[dict[str, Any]]:
    """Declared license files; a project that declares none ships its root LICENSE."""
    declared = project.get("license-files")
    if declared is None:
        declared = [p for p in _tracked_paths(checkout, rev, ".") if p == "LICENSE"]
    notices: list[dict[str, Any]] = []
    for rel in declared:
        data = _filtered_bytes(checkout, rev, rel)
        notices.append({"bytes": len(data), "path": rel, "sha256": _hash_bytes(data)})
    return notices


def _owner_project(
    checkout: Path, rev: str, pyproject: dict[str, Any], lane_name: str, init_version: str | None,
) -> dict[str, Any]:
    project = pyproject["project"]
    build = pyproject["build-system"]
    version = project.get("version") or init_version
    if not version:
        raise GeneratorError("no static [project].version and no __init__ __version__ found")
    kept, excluded = split_runtime_dependencies(lane_name, list(project.get("dependencies", [])))
    owner = {
        "build_system": {
            "build-backend": build.get("build-backend"),
            "requires": list(build.get("requires", [])),
        },
        "console_scripts": dict(project.get("scripts", {})),
        "imported_version": init_version or version,
        "license": _license_value(project),
        "license_files": _license_files(checkout, rev, project),
        "name": project["name"],
        "optional_dependencies": {
            group: list(deps)
            for group, deps in project.get("optional-dependencies", {}).items()
        },
        "pyproject_version": project.get("version"),
        "requires_python": project["requires-python"],
        "runtime_dependencies": kept,
        "version": version,
    }
    if excluded:
        owner["excluded_runtime_dependencies"] = excluded
    return owner


def _slice_keep(lane_name: str, checkout: Path, rev: str, pkg: str,
                pkg_dir: str) -> list[str] | None:
    """The package files a reviewed slice keeps, after proving the slice closed."""
    spec = slice_for(lane_name)
    if spec is None:
        return None
    keep = slice_paths(_tracked_paths(checkout, rev, pkg_dir), pkg, pkg_dir, spec["modules"])
    sources = {path: data for path, data in
               _package_blobs(checkout, rev, pkg_dir, filters=False).items() if path.endswith(".py")}
    excluded = {requirement_import_name(item["requirement"])
                for item in spec["excluded_runtime_dependencies"]}
    check_slice_closure(sources, pkg=pkg, pkg_dir=pkg_dir, modules=spec["modules"],
                        excluded_imports=excluded)
    return keep


def _admitted(lane_name: str, mcp: dict[str, Any]) -> list[str]:
    allowed = admitted_tools(lane_name)
    unknown = [t for t in allowed if t not in mcp["static_tool_names"]]
    if not allowed or unknown or mcp["health_tool"] not in allowed:
        raise GeneratorError(
            f"{lane_name}: policy admits {allowed!r}; tools not served: {unknown!r}; "
            f"health tool {mcp['health_tool']!r} must be admitted")
    return allowed


def _live_mcp(lane: Any, checkout: Path, rev: str, pkg: str, pkg_dir: str,
              keep: list[str] | None, owner: dict[str, Any], checkout_root: Path) -> dict[str, Any]:
    extra_root, extra_pkgs = studio_dependency_root(
        lane, pkg, owner["runtime_dependencies"], checkout_root)
    try:
        mcp = mcp_block(checkout, rev, lane, pkg, pkg_dir, keep=keep,
                        extra_root=extra_root, extra_pkgs=tuple(extra_pkgs))
    finally:
        if extra_root is not None:
            shutil.rmtree(extra_root, ignore_errors=True)
    mcp["allowed_tools_for_initial_admission"] = _admitted(lane.name, mcp)
    return mcp


def _descriptor(lane_name: str, mcp: dict[str, Any], source: dict[str, Any],
                version: str) -> dict[str, Any]:
    return {
        "allowed_tools": list(mcp["allowed_tools_for_initial_admission"]),
        "does_not_prove": list(DOES_NOT_PROVE),
        "entrypoint": {
            "argv": ["--bundled-lane-mcp", lane_name],
            "callable": mcp["callable"],
            "health_tool": mcp["health_tool"],
            "module": mcp["module"],
        },
        "name": lane_name,
        "schema": COMPONENT_SCHEMA,
        "source": source,
        "version": version,
    }


def _checkout(lane_name: str, checkout_root: Path) -> tuple[Any, Path]:
    if lane_name not in LANES:
        raise GeneratorError(f"unknown lane: {lane_name!r}")
    lane = LANES[lane_name]
    if not lane.source_repo:
        raise GeneratorError(f"lane {lane_name!r} has no source_repo in the registry")
    checkout = checkout_root / lane.source_repo
    if not (checkout / ".git").exists():
        raise GeneratorError(f"no git checkout at {checkout}")
    return lane, checkout


def build_row(lane_name: str, checkout_root: Path, rev: str | None) -> dict[str, Any]:
    lane, checkout = _checkout(lane_name, checkout_root)
    rev = rev or "HEAD"
    pkg_dir, pkg = _find_package_dir(checkout, rev)
    keep = _slice_keep(lane_name, checkout, rev, pkg, pkg_dir)
    source, py_paths = _source_block(checkout, rev, pkg_dir, keep)
    pyproject = tomllib.loads(_blob_bytes(checkout, rev, "pyproject.toml").decode("utf-8"))
    owner = _owner_project(checkout, rev, pyproject, lane_name,
                           _version_from_init(checkout, rev, pkg_dir))
    mcp = _live_mcp(lane, checkout, rev, pkg, pkg_dir, keep, owner, checkout_root)
    descriptor = _descriptor(lane_name, mcp, source, owner["version"])
    row = {
        "component_descriptor": descriptor,
        "component_descriptor_sha256": _digest(descriptor),
        "flywheel_registry_expected_version": lane.version,
        "hidden_imports": _hidden_imports(pkg, pkg_dir, py_paths),
        "lane": lane_name,
        "mcp": mcp,
        "owner_commit": source["commit"],
        "owner_describe": _git(checkout, "describe", "--tags", rev, text=True).strip(),
        "owner_project": owner,
        "owner_tag": _nearest_tag(checkout, rev),
        "packaging_boundary": PACKAGING_BOUNDARY,
        "registry_install_name": lane.install_name,
        "registry_package_disabled_reason": lane.package_disabled_reason,
        "registry_source_repo": lane.source_repo,
        "schema": ROW_SCHEMA,
    }
    spec = slice_for(lane_name)
    if spec is not None:
        row["payload_slice"] = {"modules": list(spec["modules"]), "reason": spec["reason"]}
    return row

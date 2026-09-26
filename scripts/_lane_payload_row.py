"""Row assembly for the Python-lane payload generator.

Builds the ``owner_project`` block, the live MCP surface block, and the full
payload row. Git/source primitives live in ``_lane_payload_source.py``; the CLI
entrypoint is ``generate_python_lane_payload_row.py``. Split for the 300-line
file gate; behavior is unchanged.
"""
from __future__ import annotations

import importlib
import inspect
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

from harness.lanes_registry import LANES
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
    _materialize,
    _mcp_module,
    _purge_modules,
    _source_block,
    _version_from_init,
)


def _license_value(project: dict[str, Any]) -> str:
    value = project.get("license")
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and isinstance(value.get("text"), str):
        return value["text"]
    raise GeneratorError("project.license is not a plain SPDX/string expression")


def _license_files(
    checkout: Path, rev: str, project: dict[str, Any]
) -> list[dict[str, Any]]:
    notices: list[dict[str, Any]] = []
    for rel in project.get("license-files", []):
        data = _filtered_bytes(checkout, rev, rel)
        notices.append({"bytes": len(data), "path": rel, "sha256": _hash_bytes(data)})
    return notices


def _owner_project(
    checkout: Path,
    rev: str,
    pyproject: dict[str, Any],
    version: str,
    imported_version: str,
) -> dict[str, Any]:
    project = pyproject["project"]
    build = pyproject["build-system"]
    return {
        "build_system": {
            "build-backend": build.get("build-backend"),
            "requires": list(build.get("requires", [])),
        },
        "console_scripts": dict(project.get("scripts", {})),
        "imported_version": imported_version,
        "license": _license_value(project),
        "license_files": _license_files(checkout, rev, project),
        "name": project["name"],
        "optional_dependencies": {
            group: list(deps)
            for group, deps in project.get("optional-dependencies", {}).items()
        },
        "pyproject_version": version,
        "requires_python": project["requires-python"],
        "runtime_dependencies": list(project.get("dependencies", [])),
        "version": version,
    }


def _health_doctor(tool_names: list[str]) -> tuple[str, str]:
    status = next((t for t in tool_names if t.endswith(".status")), None)
    doctor = next((t for t in tool_names if t.endswith(".doctor")), None)
    if not status or not doctor:
        raise GeneratorError(
            f"lane exposes no status/doctor health tools (tools={tool_names!r})"
        )
    return status, doctor


def _tool_surface(module: Any, module_name: str) -> tuple[list[str], str]:
    """Read (static_tool_names, callable_style) from a bundled-lane MCP module."""
    if not hasattr(module, "serve"):
        raise GeneratorError(
            f"MCP module {module_name!r} has no 'serve' callable (bundled-lane convention)"
        )
    # Older lanes name the JSON-RPC dispatcher handle_request; newer lane
    # releases (relay 0.2, plexus 0.2, canon 0.2) name it handle. The runtime
    # only calls serve, so either name gives the generator the tool list.
    handler = getattr(module, "handle_request", None) or getattr(module, "handle", None)
    if handler is None:
        raise GeneratorError(
            f"MCP module {module_name!r} has no 'handle_request' or 'handle' tools/list "
            "handler (bundled-lane convention)"
        )
    response = handler({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    try:
        tool_names = [tool["name"] for tool in response["result"]["tools"]]
    except (TypeError, KeyError) as exc:
        raise GeneratorError(
            f"MCP module {module_name!r} tools/list returned no tool list: {response!r}"
        ) from exc
    style = "async" if inspect.iscoroutinefunction(module.serve) else "sync"
    return tool_names, style


def _mcp_block(checkout: Path, rev: str, lane: Any, pkg: str, pkg_dir: str) -> dict[str, Any]:
    """Import the pinned lane source and read its live MCP surface."""
    module_name = _mcp_module(lane, pkg)
    tmp = _materialize(checkout, rev, pkg_dir)
    import_root = str(tmp / pkg_dir.rsplit("/", 1)[0]) if "/" in pkg_dir else str(tmp)
    sys.path.insert(0, import_root)
    _purge_modules(pkg)
    try:
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            # A `<command> mcp` lane may serve from <pkg>.local_mcp (canon 0.2).
            fallback = f"{pkg}.local_mcp"
            if exc.name != module_name or module_name != f"{pkg}.mcp":
                raise GeneratorError(f"MCP module {module_name!r} import failed: {exc!r}") from exc
            try:
                module = importlib.import_module(fallback)
            except Exception as exc2:  # noqa: BLE001 - report the real import failure
                raise GeneratorError(
                    f"MCP module {module_name!r} missing and {fallback!r} import failed: {exc2!r}"
                ) from exc2
            module_name = fallback
        except Exception as exc:  # noqa: BLE001 - report the real import failure
            raise GeneratorError(f"MCP module {module_name!r} import failed: {exc!r}") from exc
        tool_names, style = _tool_surface(module, module_name)
    finally:
        if import_root in sys.path:
            sys.path.remove(import_root)
        _purge_modules(pkg)
        shutil.rmtree(tmp, ignore_errors=True)
    health, doctor = _health_doctor(tool_names)
    contract = (
        "async_coroutine_runtime_dispatch"
        if style == "async"
        else "compatible_with_sync_dispatcher"
    )
    return {
        "allowed_tools_for_initial_admission": [health, doctor],
        "callable": "serve",
        "callable_style": style,
        "contract_status": contract,
        "doctor_tool": doctor,
        "health_tool": health,
        "module": module_name,
        "static_tool_names": tool_names,
    }


def build_row(lane_name: str, checkout_root: Path, rev: str | None) -> dict[str, Any]:
    if lane_name not in LANES:
        raise GeneratorError(f"unknown lane: {lane_name!r}")
    lane = LANES[lane_name]
    if not lane.source_repo:
        raise GeneratorError(f"lane {lane_name!r} has no source_repo in the registry")
    checkout = checkout_root / lane.source_repo
    if not (checkout / ".git").exists():
        raise GeneratorError(f"no git checkout at {checkout}")
    rev = rev or "HEAD"

    pkg_dir, pkg = _find_package_dir(checkout, rev)
    commit = _git(checkout, "rev-parse", rev, text=True).strip()
    describe = _git(checkout, "describe", "--tags", rev, text=True).strip()

    source, py_paths = _source_block(checkout, rev, pkg_dir)
    pyproject = tomllib.loads(_blob_bytes(checkout, rev, "pyproject.toml").decode("utf-8"))
    init_version = _version_from_init(checkout, rev, pkg_dir)
    version = pyproject["project"].get("version") or init_version
    if not version:
        raise GeneratorError("no static [project].version and no __init__ __version__ found")
    imported_version = init_version or version
    owner_project = _owner_project(checkout, rev, pyproject, version, imported_version)
    mcp = _mcp_block(checkout, rev, lane, pkg, pkg_dir)

    health, doctor = mcp["health_tool"], mcp["doctor_tool"]
    descriptor = {
        "allowed_tools": [health, doctor],
        "does_not_prove": list(DOES_NOT_PROVE),
        "entrypoint": {
            "argv": ["--bundled-lane-mcp", lane_name],
            "callable": mcp["callable"],
            "health_tool": health,
            "module": mcp["module"],
        },
        "name": lane_name,
        "schema": COMPONENT_SCHEMA,
        "source": source,
        "version": owner_project["version"],
    }

    return {
        "component_descriptor": descriptor,
        "component_descriptor_sha256": _digest(descriptor),
        "flywheel_registry_expected_version": lane.version,
        "hidden_imports": _hidden_imports(pkg, pkg_dir, py_paths),
        "lane": lane_name,
        "mcp": mcp,
        "owner_commit": commit,
        "owner_describe": describe,
        "owner_project": owner_project,
        "owner_tag": describe,
        "packaging_boundary": PACKAGING_BOUNDARY,
        "registry_install_name": lane.install_name,
        "registry_package_disabled_reason": lane.package_disabled_reason,
        "registry_source_repo": lane.source_repo,
        "schema": ROW_SCHEMA,
    }

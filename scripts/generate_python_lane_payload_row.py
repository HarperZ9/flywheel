"""Generate a Python-lane payload JSONL row for Flywheel's native bundle.

Given a lane name, emit the full ``packaging/python-lane-payloads.jsonl`` row for
it, derived from the lane registry plus the lane's own source checkout. The row
structure matches the rows already committed to that manifest and is validated by
``scripts/check_python_lane_payload_manifest.py``.

Source facts are read from the git object store at a pinned revision, not from the
working tree, so a dirty or advanced checkout does not perturb the evidence. File
bytes are read through the repo's checkout filters (``git cat-file --filters``) so
the recorded byte counts and hashes match a real on-disk checkout (autocrlf and
``.gitattributes`` applied), which is how the committed rows were built.

Reproduction: run this for ``gather`` at ``v1.8.2`` and ``crucible`` at ``v1.2.0``
(the revisions their committed rows pin) and the output is byte-identical to the
committed lines. The working checkouts have since advanced past those tags, so
``--rev`` selects the revision; it defaults to the checkout HEAD.
"""
from __future__ import annotations

import argparse
import ast
import importlib
import inspect
import json
import shutil
import subprocess
import sys
import tempfile
import tomllib
from hashlib import sha256
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.evidence_json import canonical_sha256
from harness.lanes_registry import LANES

SOURCE_ALGORITHM = "sha256-canonical-source-manifest/v1"
COMPONENT_SCHEMA = "flywheel.bundled-lane-component/v1"
ROW_SCHEMA = "flywheel.python-lane-payload/v1"
PACKAGING_BOUNDARY = (
    "source_pin_and_manifest_only_no_runtime_admission_until_runtime_contract"
    "_extends_python_sidecars"
)
DOES_NOT_PROVE = [
    "NOT_PROVES_FULL_LANE_WORKFLOW: status and doctor admission checks identity/readiness only.",
    "NOT_PROVES_RUNTIME_DEPENDENCY_CLOSURE: interpreter, wheels, and import closure are bound by a separate installed release receipt.",
    "NOT_PROVES_PROVIDER_DEVICE_OR_PRIVATE_DATA_READINESS: no provider, device, account, model, or private-data operation is exercised.",
]


class GeneratorError(RuntimeError):
    pass


def _git(checkout: Path, *args: str, text: bool = False) -> Any:
    proc = subprocess.run(
        ["git", "-C", str(checkout), *args],
        capture_output=True,
        text=text,
    )
    if proc.returncode != 0:
        detail = proc.stderr if text else proc.stderr.decode("utf-8", "replace")
        raise GeneratorError(f"git {' '.join(args)} failed: {detail.strip()}")
    return proc.stdout


def _digest(value: Any) -> str:
    return "sha256:" + canonical_sha256(value)


def _hash_bytes(data: bytes) -> str:
    return "sha256:" + sha256(data).hexdigest()


def _filtered_bytes(checkout: Path, rev: str, path: str) -> bytes:
    """The bytes a checkout would write for ``path`` (autocrlf/.gitattributes)."""
    return _git(checkout, "cat-file", "--filters", f"{rev}:{path}")


def _blob_bytes(checkout: Path, rev: str, path: str) -> bytes:
    return _git(checkout, "cat-file", "blob", f"{rev}:{path}")


def _tracked_paths(checkout: Path, rev: str, subdir: str) -> list[str]:
    out = _git(checkout, "ls-tree", "-r", "--name-only", "-z", rev, subdir)
    return sorted(p for p in out.decode("utf-8").split("\0") if p)


TEST_DIR_NAMES = {"tests", "test"}


def _find_package_dir(checkout: Path, rev: str) -> tuple[str, str]:
    """Return (package_dir, package_name); prefer src/<pkg>, else root-level <pkg>/."""
    inits = [p for p in _tracked_paths(checkout, rev, ".") if p.endswith("__init__.py")]
    src_pkgs = sorted(
        {
            p.split("/")[1]
            for p in inits
            if p.count("/") == 2 and p.startswith("src/") and p.split("/")[1] not in TEST_DIR_NAMES
        }
    )
    if len(src_pkgs) == 1:
        return f"src/{src_pkgs[0]}", src_pkgs[0]
    root_pkgs = sorted(
        {
            p.split("/")[0]
            for p in inits
            if p.count("/") == 1 and p.split("/")[0] not in TEST_DIR_NAMES
        }
    )
    if len(root_pkgs) == 1:
        return root_pkgs[0], root_pkgs[0]
    raise GeneratorError(
        f"cannot uniquely locate package dir (src candidates={src_pkgs!r}, "
        f"root candidates={root_pkgs!r})"
    )


def _mcp_module(lane: Any, pkg: str) -> str:
    """The module that serves the bundled-lane MCP, derived from the registry entry.

    - ``<command> mcp`` subcommand lanes serve from ``<pkg>.mcp``.
    - ``python -m <module>`` lanes serve from that ``-m`` module.
    - otherwise the registry ``py_module`` is taken as the serving module.
    """
    args = list(lane.mcp_args)
    if "mcp" in args:
        return f"{pkg}.mcp"
    if lane.command == "python" and len(args) >= 2 and args[0] == "-m":
        return args[1]
    if lane.py_module:
        return lane.py_module
    raise GeneratorError(f"cannot determine MCP module for lane {lane.name!r} from registry")


def _source_block(checkout: Path, rev: str, pkg_dir: str) -> tuple[dict[str, Any], list[str]]:
    commit = _git(checkout, "rev-parse", rev, text=True).strip()
    repo = _git(checkout, "remote", "get-url", "origin", text=True).strip()
    files: list[dict[str, Any]] = []
    py_paths: list[str] = []
    for path in _tracked_paths(checkout, rev, pkg_dir):
        data = _filtered_bytes(checkout, rev, path)
        files.append({"bytes": len(data), "path": path, "sha256": _hash_bytes(data)})
        if path.endswith(".py"):
            py_paths.append(path)
    files.sort(key=lambda item: item["path"])
    source = {
        "algorithm": SOURCE_ALGORITHM,
        "bytes": sum(item["bytes"] for item in files),
        "commit": commit,
        "file_count": len(files),
        "files": files,
        "manifest_sha256": _digest(files),
        "path": pkg_dir,
        "repo": repo,
    }
    return source, py_paths


def _hidden_imports(pkg: str, pkg_dir: str, py_paths: list[str]) -> list[str]:
    modules: set[str] = set()
    for path in py_paths:
        rel = path[len(pkg_dir) + 1 :][: -len(".py")]
        parts = [part for part in rel.split("/")]
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        modules.add(".".join([pkg, *parts]) if parts else pkg)
    return sorted(modules)


def _version_from_init(checkout: Path, rev: str, pkg_dir: str) -> str | None:
    try:
        src = _blob_bytes(checkout, rev, f"{pkg_dir}/__init__.py").decode("utf-8")
    except GeneratorError:
        return None
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if "__version__" in targets and isinstance(node.value, ast.Constant):
                if isinstance(node.value.value, str):
                    return node.value.value
    return None


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


def _materialize(checkout: Path, rev: str, pkg_dir: str) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="flywheel_lane_pkg_"))
    for path in _tracked_paths(checkout, rev, pkg_dir):
        dst = tmp / path
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(_blob_bytes(checkout, rev, path))
    return tmp


def _purge_modules(pkg: str) -> None:
    for name in [m for m in list(sys.modules) if m == pkg or m.startswith(pkg + ".")]:
        del sys.modules[name]


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
    if not hasattr(module, "handle_request"):
        raise GeneratorError(
            f"MCP module {module_name!r} has no 'handle_request' tools/list handler "
            "(bundled-lane convention)"
        )
    response = module.handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
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
        "needs_async_dispatch_or_wrapper"
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


def _emit(row: dict[str, Any]) -> str:
    return json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lane", help="lane name (e.g. gather, crucible)")
    parser.add_argument(
        "--checkout-root",
        default="C:/dev",
        help="root that holds <source_repo> checkouts (default: C:/dev)",
    )
    parser.add_argument(
        "--rev",
        default=None,
        help="git revision to pin (default: the checkout HEAD)",
    )
    args = parser.parse_args(argv)
    try:
        row = build_row(args.lane, Path(args.checkout_root), args.rev)
    except GeneratorError as exc:
        print(json.dumps({"verdict": "FAIL", "error": str(exc)}, sort_keys=True))
        return 1
    print(_emit(row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

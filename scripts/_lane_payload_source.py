"""Source-manifest and git primitives for the Python-lane payload row generator.

Split out of ``generate_python_lane_payload_row.py`` so every file stays under the
repo's 300-line gate. This module holds the git object-store readers, the source
manifest builder, package discovery, hidden-import derivation, and the pinned-
source materializer. Row assembly lives in ``_lane_payload_row.py`` and the CLI is
``generate_python_lane_payload_row.py``. The split is structural; behavior is
unchanged.
"""
from __future__ import annotations

import ast
import subprocess
import sys
import tempfile
from hashlib import sha256
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
for _p in (str(_ROOT), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from harness.evidence_json import canonical_sha256

SOURCE_ALGORITHM = "sha256-canonical-source-manifest/v1"
COMPONENT_SCHEMA = "flywheel.bundled-lane-component/v1"
ROW_SCHEMA = "flywheel.python-lane-payload/v1"
PACKAGING_BOUNDARY = (
    "source_pinned_vendored_runtime_admission_all_python_lanes"
    "_status_doctor_tools_only"
)
DOES_NOT_PROVE = [
    "NOT_PROVES_FULL_LANE_WORKFLOW: status and doctor admission checks identity/readiness only.",
    "NOT_PROVES_RUNTIME_DEPENDENCY_CLOSURE: interpreter, wheels, and import closure are bound by a separate installed release receipt.",
    "NOT_PROVES_PROVIDER_DEVICE_OR_PRIVATE_DATA_READINESS: no provider, device, account, model, or private-data operation is exercised.",
]
TEST_DIR_NAMES = {"tests", "test"}


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
    """The bytes a reproducible cross-platform checkout writes for ``path``.

    ``stage_python_lane_sources.py`` clones each pinned source with
    ``core.autocrlf=false`` and ``core.eol=lf`` and then re-hashes the on-disk
    bytes, so its verification runs against the working tree those exact settings
    produce on every platform. This generator reads the same bytes by asking
    ``git cat-file --filters`` to apply that identical config. A plain
    ``cat-file --filters`` would instead use the current repo's config, which
    under ``core.autocrlf=true`` (the Windows default) yields CRLF and makes the
    recorded hash fail closed when the lane is staged. Pinning the config here,
    rather than blindly rewriting CRLF to LF, is what mirrors staging: it honors
    ``.gitattributes``, so a file marked ``-text`` (byte-pinned release material)
    keeps its exact bytes instead of being corrupted by line-ending
    normalization. A row is therefore byte-identical whether it is generated on a
    Windows checkout or a Linux one, and stages cleanly on both.
    """
    return _git(
        checkout, "-c", "core.autocrlf=false", "-c", "core.eol=lf",
        "cat-file", "--filters", f"{rev}:{path}")


def _blob_bytes(checkout: Path, rev: str, path: str) -> bytes:
    return _git(checkout, "cat-file", "blob", f"{rev}:{path}")


def _tracked_paths(checkout: Path, rev: str, subdir: str) -> list[str]:
    out = _git(checkout, "ls-tree", "-r", "--name-only", "-z", rev, subdir)
    return sorted(p for p in out.decode("utf-8").split("\0") if p)


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

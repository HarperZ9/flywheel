"""Admission and dispatch for lanes carried inside the frozen gateway payload.

The gateway can launch a bundled lane's reviewed source as a self-child, but
only after its descriptor agrees with an expectation the build trusts and its
module is importable. This module is lane-general: relay keeps its compiled
expectation and ``bundled-lanes/relay.json`` descriptor, and every other lane is
resolved from its pinned ``python-lane-payloads`` manifest row. Descriptor
validation and expectation resolution live in ``bundled_lane_descriptor``; this
file is the orchestration (child environment, admission, dispatch) plus the
relay descriptor builder used by the build-time gate.
"""
from __future__ import annotations

from dataclasses import dataclass
import asyncio
import hashlib
import importlib
import inspect
import os
from pathlib import Path
import re
import sys
import tomllib
from typing import Callable, Mapping

from . import bundled_lane_descriptor as _descriptor
from .bundled_lane_descriptor import (  # re-exported for scripts and tests
    SCHEMA, SOURCE_ALGORITHM, canonical_descriptor_text, descriptor_digest)
from .evidence_json import canonical_sha256
from .mcp_client import LaunchSpec

ADMITTED_BUNDLED_RELAY_TOOLS = ("relay.status",)
_SAFE_LANE = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
DOES_NOT_PROVE = (
    "NOT_PROVES_REPLACEMENT_OF_TRUSTED_EXECUTABLE: the descriptor binds the "
    "reviewed Relay source included in this build, not a later replacement of "
    "the whole gateway executable.",
    "NOT_PROVES_AGENTIC_TASK_SUCCESS: relay.status is an identity and "
    "transport check, not proof that Relay can complete model-backed work.",
    "NOT_PROVES_PROVIDER_OR_NETWORK_READINESS: the status check is "
    "network-free and carries no provider credential custody.",
)


@dataclass(frozen=True)
class BundledLaneAdmission:
    launch: LaunchSpec | None
    component: dict | None
    blocking_codes: tuple[str, ...]


def bundled_child_environment(
        environ: Mapping[str, str], *, platform: str = os.name) -> dict[str, str]:
    """Return the small environment passed to a bundled lane child."""
    if platform == "nt":
        retained = {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "SYSTEMDRIVE",
                    "TEMP", "TMP", "USERPROFILE", "APPDATA", "LOCALAPPDATA"}
        env = {key: str(value) for key, value in environ.items()
               if key.upper() in retained}
        root = env.get("SYSTEMROOT") or env.get("WINDIR") or "C:/Windows"
        env["PATH"] = str(Path(root) / "System32").replace("\\", "/")
        return env
    retained = {"LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "TEMP", "TMP"}
    env = {key: str(value) for key, value in environ.items() if key in retained}
    env["PATH"] = os.defpath
    return env


def admit_bundled_lane(
    name: str,
    *,
    executable: str,
    environ: Mapping[str, str],
    descriptor_path: str | Path | None = None,
    importable_fn: Callable[[str], bool] | None = None,
    expected: Mapping[str, object] | None = None,
    manifest_rows: Mapping[str, dict] | None = None,
) -> BundledLaneAdmission:
    """Admit one frozen bundled lane only when descriptor and module agree."""
    descriptor, expected_row, load_codes = _descriptor.resolve_bundled_lane(
        name, descriptor_path=descriptor_path, expected=expected,
        manifest_rows=manifest_rows)
    if descriptor is None or expected_row is None:
        return BundledLaneAdmission(None, None, load_codes)
    codes = list(load_codes)
    codes.extend(_descriptor.validate_descriptor(name, descriptor, expected_row))
    module_name = str(expected_row.get("module", ""))
    if not module_name:
        codes.append("bundled_entrypoint_invalid")
    elif not (importable_fn or _descriptor.module_importable)(module_name):
        codes.append("bundled_module_missing")
    codes = list(dict.fromkeys(codes))
    if codes:
        return BundledLaneAdmission(None, None, tuple(codes))
    component = _descriptor.component_summary(descriptor, expected_row)
    launch = LaunchSpec(
        (executable, "--bundled-lane-mcp", name),
        env_overrides=tuple(sorted(bundled_child_environment(environ).items())),
        inherit_env=False,
        hide_window=True,
        allowed_tools=tuple(expected_row["allowed_tools"]),
    )
    return BundledLaneAdmission(launch, component, ())


def dispatch_bundled_lane_mcp(
    argv: list[str] | tuple[str, ...] | None = None,
    *,
    import_module_fn: Callable[[str], object] = importlib.import_module,
    executable: str | None = None,
    environ: Mapping[str, str] | None = None,
    descriptor_path: str | Path | None = None,
    expected: Mapping[str, object] | None = None,
    manifest_rows: Mapping[str, dict] | None = None,
) -> int | None:
    """Serve one bundled lane child mode, or return None for the normal gateway.

    The child mode is exactly ``--bundled-lane-mcp <lane>`` (two tokens, a safe
    lane name). Any manifest lane admits and serves through this one path; the
    lane must clear the same admission as launch, and its declared callable is
    run. A synchronous callable runs directly; an async coroutine callable (such
    as forum's ``serve_stdio``) runs to completion under ``asyncio.run`` in this
    child process, which owns no other event loop. A non-coroutine awaitable is
    refused, since it has no defined run contract here."""
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] != "--bundled-lane-mcp":
        return None
    if len(args) != 2 or not _SAFE_LANE.fullmatch(args[1]):
        return 2
    name = args[1]
    expected_row = _descriptor.resolve_expected(
        name, expected=expected, manifest_rows=manifest_rows)
    if expected_row is None:
        return 2
    admission = admit_bundled_lane(
        name,
        executable=executable or sys.executable,
        environ=environ or os.environ,
        descriptor_path=descriptor_path,
        expected=expected_row,
        manifest_rows=manifest_rows,
    )
    if admission.blocking_codes:
        return 2
    module = import_module_fn(str(expected_row["module"]))
    serve = getattr(module, str(expected_row["callable"]), None)
    if not callable(serve):
        return 2
    result = serve()
    if inspect.iscoroutine(result):
        return int(asyncio.run(result) or 0)
    if inspect.isawaitable(result):
        getattr(result, "close", lambda: None)()
        return 2
    return int(result or 0)


def build_relay_descriptor(source_root: Path, *, commit: str) -> dict:
    """Build the canonical descriptor for the Relay source tree at ``source_root``."""
    source_root = source_root.resolve()
    version = _pyproject_version(source_root / "pyproject.toml")
    files = source_manifest(source_root / "src" / "relay", relative_to=source_root)
    source = {
        "repo": "https://github.com/HarperZ9/relay",
        "commit": commit,
        "path": "src/relay",
        "algorithm": SOURCE_ALGORITHM,
        "file_count": len(files),
        "bytes": sum(int(row["bytes"]) for row in files),
        "files": files,
        "manifest_sha256": "sha256:" + canonical_sha256(files),
    }
    return {
        "schema": SCHEMA,
        "name": "relay",
        "version": version,
        "source": source,
        "entrypoint": {
            "argv": ["--bundled-lane-mcp", "relay"],
            "module": "relay.local_mcp",
            "callable": "serve",
            "health_tool": "relay.status",
        },
        "allowed_tools": list(ADMITTED_BUNDLED_RELAY_TOOLS),
        "does_not_prove": list(DOES_NOT_PROVE),
    }


def source_manifest(root: Path, *, relative_to: Path) -> list[dict[str, object]]:
    root = root.resolve()
    base = relative_to.resolve()
    rows: list[dict[str, object]] = []
    for path in sorted(root.rglob("*.py")):
        if not path.is_file():
            continue
        data = path.read_bytes()
        rows.append({
            "path": path.relative_to(base).as_posix(),
            "bytes": len(data),
            "sha256": "sha256:" + hashlib.sha256(data).hexdigest(),
        })
    return rows


def _pyproject_version(path: Path) -> str:
    try:
        value = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValueError("Relay pyproject version is unreadable") from exc
    version = value.get("project", {}).get("version")
    if not isinstance(version, str) or not version:
        raise ValueError("Relay pyproject version is missing")
    return version

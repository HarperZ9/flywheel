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
from . import bundled_lane_env as _bundled_env
from .bundled_lane_descriptor import (  # re-exported for scripts and tests
    SCHEMA, SOURCE_ALGORITHM, canonical_descriptor_text, descriptor_digest)
from .evidence_json import canonical_sha256
from .lane_tool_policy import admitted_tools
from .mcp_client import LaunchSpec

# Relay's T1 tools from the lane tool policy. local_agent_start, _status and
# _result stay out (a background run dies with the per-call child, WP10 and O-3).
ADMITTED_BUNDLED_RELAY_TOOLS = tuple(admitted_tools("relay"))
_SAFE_LANE = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
DOES_NOT_PROVE = (
    "NOT_PROVES_REPLACEMENT_OF_TRUSTED_EXECUTABLE: the descriptor binds the "
    "reviewed Relay source included in this build, not a later replacement of "
    "the whole gateway executable.",
    "NOT_PROVES_AGENTIC_TASK_SUCCESS: admitting Relay's T1 tools checks identity "
    "and transport, not that Relay completes model-backed work.",
    "NOT_PROVES_PROVIDER_OR_NETWORK_READINESS: no provider credential rides the "
    "launch; a model server is a separate setup item.",
    "NOT_PROVES_SHELL_CONFINEMENT: relay 0.5.0 takes write and exec from its "
    "launch, and the engine launches it with both off, its root at the lane "
    "folder, no RELAY_CHILD_ENV names and no unproven CLI tier allowed; the "
    "engine also passes only listed arguments, so root, check, test_cmd and "
    "online never reach a run, and no shell, bisect or git child starts. relay's "
    "shell is not path-confined when a launch grants exec, which this build "
    "never does.",
    "NOT_PROVES_BACKGROUND_RUN_DURABILITY: a local_agent_start run lives in the "
    "memory of the relay lane session; when that session ends (idle, a crash, "
    "an engine stop) the run ends with it and its id reads unknown.",
)


@dataclass(frozen=True)
class BundledLaneAdmission:
    launch: LaunchSpec | None
    component: dict | None
    blocking_codes: tuple[str, ...]


def bundled_child_environment(
        environ: Mapping[str, str], *, platform: str = os.name,
        lane: str | None = None) -> dict[str, str]:
    """Return the small environment passed to a bundled lane child.

    The base set, the Flywheel home, UTF-8 stdio and, for a lane that needs it,
    the Git folder; the rules live in bundled_lane_env."""
    return _bundled_env.bundled_child_environment(environ, platform=platform, lane=lane)


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
        env_overrides=tuple(sorted(bundled_child_environment(environ, lane=name).items())),
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

    External clients use exactly ``--bundled-lane-mcp articulate --local-only``.
    This forces Articulate's local profile before admission can import it.
    The legacy internal mode is ``--bundled-lane-mcp <lane>`` (a safe lane name),
    followed only by launch grants the policy names for that lane, each at most
    once (``lane_tool_policy_args.LAUNCH_GRANTS``; the engine adds one to the
    launch of a granted T2 call). Each grant reaches the callable as its keyword
    set to True, the way forum's ``--allow-gate-decisions`` reaches
    ``serve_stdio(allow_gate_decisions=True)``. Any other token refuses the child.
    Any manifest lane admits and serves through this one path; the
    lane must clear the same admission as launch, and its declared callable is
    run. A synchronous callable runs directly; an async coroutine callable (such
    as forum's ``serve_stdio``) runs to completion under ``asyncio.run`` in this
    child process, which owns no other event loop. A non-coroutine awaitable is
    refused, since it has no defined run contract here."""
    args = list(sys.argv[1:] if argv is None else argv)
    local_only = "--local-only" in args
    if local_only and args != ["--bundled-lane-mcp", "articulate", "--local-only"]:
        return 2
    if not args or args[0] != "--bundled-lane-mcp":
        if "--bundled-lane-mcp" in args:
            return 2
        return None
    if len(args) < 2 or not _SAFE_LANE.fullmatch(args[1]):
        return 2
    name = args[1]
    grants = {} if local_only else _launch_grant_keywords(name, args[2:])
    if grants is None:
        return 2
    expected_row = _descriptor.resolve_expected(
        name, expected=expected, manifest_rows=manifest_rows)
    if expected_row is None:
        return 2
    if local_only:
        # This dispatcher runs in the dedicated stdio child. Override inherited
        # values before find_spec can import the package, not just before serve.
        os.environ["ARTICULATE_MCP_TOOLS"] = "local"
        os.environ["ARTICULATE_LOCAL_ONLY"] = "1"
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
    from . import lane_worker_mode
    lane_worker_mode.install_worker_spawn(name)   # a router job's worker (WP10)
    module = import_module_fn(str(expected_row["module"]))
    serve = getattr(module, str(expected_row["callable"]), None)
    if not callable(serve):
        return 2
    result = serve(**grants)
    if inspect.iscoroutine(result):
        return int(asyncio.run(result) or 0)
    if inspect.isawaitable(result):
        getattr(result, "close", lambda: None)()
        return 2
    return int(result or 0)


def _launch_grant_keywords(lane: str, extra: list[str]) -> dict[str, bool] | None:
    """The serve keywords for the launch grants after the lane name, or None
    when a token is not a grant the policy names for this lane or repeats."""
    from .lane_tool_policy_args import LAUNCH_GRANTS
    known = LAUNCH_GRANTS.get(lane, {})
    if len(set(extra)) != len(extra) or any(flag not in known for flag in extra):
        return None
    return {known[flag]: True for flag in extra}


def build_relay_descriptor(source_root: Path, *, commit: str,
                           files: list[dict[str, object]] | None = None) -> dict:
    """Build the canonical descriptor for the Relay source tree at ``source_root``.

    ``files`` is the source manifest when the caller read it from the commit
    itself (``check_bundled_lane_descriptors`` reads the LF bytes a
    reproducible checkout writes); without it the working tree is hashed."""
    source_root = source_root.resolve()
    version = _pyproject_version(source_root / "pyproject.toml")
    if files is None:
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

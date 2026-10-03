"""Runtime selection for source- and package-backed lanes.

A lane is one MCP tool server the gateway can launch, and the same lane can run
more than one way. This module decides which, via the "runtime profile" in the
per-lane registry row:

  - "auto" (the default): prefer a resolvable source checkout, else the package.
  - "source": force the source checkout; block the lane if none resolves.
  - "package": force the installed package at its expected version.

An unknown profile is a blocking error, so a typo cannot widen what launches.
resolve_lane_runtime launches nothing: it returns a ResolvedLaneRuntime with the
launch it would perform, plus mismatch_codes (every anomaly noticed) and
blocking_codes (the subset that makes the lane unusable; see _blocking_codes).
The pure helpers it calls live in lane_runtime_support.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from . import lane_runtime_frozen as _frozen
from . import lane_runtime_support as _support
from .lane_env import confine_lane_launch
from .lane_runtime_versions import validate_public_version, version_below
from .lanes_registry import Lane
from .mcp_client import LaunchSpec

RUNTIME_SCHEMA = "flywheel.lane-runtime/v1"
UNPROBED_CAPABILITY = _support.UNPROBED_CAPABILITY
resolve_repo = _support.resolve_repo
resolve_source_repo = _support.resolve_source_repo
extra_import_roots = _support.extra_import_roots
importable = _support.importable
frozen = _support.frozen
installed_version = _support.installed_version
package_runtime_version = _support.package_runtime_version
python_import_root = _support.python_import_root
pip_mcp_command = _support.pip_mcp_command
capability_summary = _support.capability_summary
_VALID_PROFILES = {"auto", "source", "package"}


class LaneRuntimeError(RuntimeError):
    """An explicit lane runtime selector cannot be honored."""

    def __init__(self, lane_name: str, codes: tuple[str, ...]):
        self.lane_name = lane_name
        self.codes = codes
        super().__init__(f"{lane_name} runtime selection failed: {', '.join(codes)}")


@dataclass(frozen=True)
class ResolvedLaneRuntime:
    """The resolved-but-not-launched runtime for one lane. selected_runtime
    names the chosen path; mismatch_codes lists every anomaly noticed and
    blocking_codes is the subset that prevents use, so a recorded version drift
    stays visible without the lane being refused over it."""
    name: str
    launch: LaunchSpec | None
    selected_profile: str
    selection_source: str
    selected_runtime: str
    expected_version: str | None
    runtime_expected_version: str | None
    installed_version: str | None
    source_available: bool
    package_available: bool
    source_selected: bool
    source_version: str | None
    mismatch_codes: tuple[str, ...]
    blocking_codes: tuple[str, ...]
    bundled_component: dict | None = None

    @property
    def present(self) -> bool:
        """True when a real runtime was chosen and nothing blocks it. A version
        mismatch alone does not make a lane absent; a blocking code does."""
        return self.selected_runtime in {"source", "package", "bundled", "http"} and not self.blocking_codes

    def require_launch(self) -> LaunchSpec:
        """Return the launch spec, or raise if the lane is blocked or has none,
        so the gateway fails closed instead of launching an unusable lane."""
        if self.blocking_codes or self.launch is None:
            raise LaneRuntimeError(self.name, self.blocking_codes or ("runtime_launch_missing",))
        return self.launch

    def to_dict(self, capability: dict | None = None) -> dict:
        """Serialize the resolution for the registry and telemetry. The launch is
        reduced to a shape summary (launch_summary) so no absolute path or env
        value leaks into a stored record."""
        row = {
            "schema": RUNTIME_SCHEMA,
            "selected_profile": self.selected_profile,
            "selection_source": self.selection_source,
            "selected_runtime": self.selected_runtime,
            "expected_version": self.expected_version,
            "runtime_expected_version": self.runtime_expected_version,
            "installed_version": self.installed_version,
            "source_available": self.source_available,
            "package_available": self.package_available,
            "source_selected": self.source_selected,
            "source_version": self.source_version,
            "launch": _support.launch_summary(self.launch),
            "capability": dict(capability or UNPROBED_CAPABILITY),
            "mismatch_codes": list(self.mismatch_codes),
        }
        if self.bundled_component is not None:
            row["bundled_component"] = dict(self.bundled_component)
        return row


def resolve_lane_runtime(
    name: str,
    lanes: Mapping[str, Lane],
    registry: Mapping[str, Any],
    *,
    environ: Mapping[str, str],
    python_executable: str,
    is_frozen: bool,
    source_resolver: Callable[[Lane], Path | None],
    extra_roots: Callable[[Lane], list[str]],
    importable_fn: Callable[[str], bool],
    installed_version_fn: Callable[[Lane], str | None],
    package_runtime_version_fn: Callable[[Lane, str], str | None],
) -> ResolvedLaneRuntime:
    """Resolve one lane's runtime without launching it. Every observation is
    injected, so this stays testable and free of direct environment reads. It picks
    a launch via _select_launch, confines a pip or npm launch to the minimal env
    (lane_env.py), then asks _blocking_codes which codes are fatal."""
    lane = lanes[name]
    row, row_codes = _registry_row(registry.get(name))
    profile, selection_source, profile_codes = _runtime_profile(row)
    source = source_resolver(lane)
    expected, expected_codes = validate_public_version(
        lane.version, "expected_version_invalid")
    raw_source_version = _support.source_runtime_version(lane, source) if source else None
    source_version, source_codes = (
        validate_public_version(raw_source_version, "source_version_invalid")
        if raw_source_version is not None else (None, ()))
    runtime_expected, version_codes = _runtime_expected_version(row, expected, profile)
    runtime_python, python_codes = _runtime_python(row)
    raw_installed = None if lane.package_disabled_reason else _observed_package_version(
        lane, runtime_python, installed_version_fn, package_runtime_version_fn)
    installed, installed_codes = (
        validate_public_version(raw_installed, "installed_version_invalid")
        if raw_installed is not None else (None, ()))
    package_available = installed is not None or lane.kind == "bundled"
    mismatch = [
        *row_codes, *expected_codes, *profile_codes, *source_codes,
        *version_codes, *python_codes, *installed_codes,
    ]
    mismatch += _version_codes(lane, expected, source_version, installed, runtime_expected)
    launch, selected, bundled_component, bundled_codes = _select_launch(
        lane, profile, source, python_executable, environ, is_frozen,
        extra_roots, importable_fn, runtime_python)
    launch, env_codes = confine_lane_launch(lane, launch, environ, row)
    blocking = _blocking_codes(
        lane, profile, selected, bool(source), package_available,
        [*mismatch, *bundled_codes])
    blocking = tuple(dict.fromkeys(blocking))
    all_codes = tuple(dict.fromkeys([*mismatch, *env_codes, *bundled_codes, *blocking]))
    return ResolvedLaneRuntime(
        name=name, launch=launch, selected_profile=profile,
        selection_source=selection_source, selected_runtime=selected,
        expected_version=expected, runtime_expected_version=runtime_expected,
        installed_version=installed, source_available=source is not None,
        package_available=package_available, source_selected=selected == "source",
        source_version=source_version, mismatch_codes=all_codes,
        blocking_codes=blocking, bundled_component=bundled_component,
    )


def _version_codes(lane, expected, source_version, installed, runtime_expected) -> list[str]:
    """A source or installed version off its pin; below the pin is named too."""
    codes = ["source_version_mismatch"] if (
        source_version and expected and source_version != expected) else []
    if installed and runtime_expected and installed != runtime_expected and lane.kind in {"pip", "npm"}:
        codes.append("installed_version_mismatch")
        if version_below(installed, runtime_expected):
            codes.append("installed_version_below_pin")
    return codes


def _registry_row(value: object) -> tuple[dict, tuple[str, ...]]:
    """The per-lane registry entry as a dict; a non-dict is a named mismatch."""
    if value is None:
        return {}, ()
    if isinstance(value, dict):
        return value, ()
    return {}, ("registry_row_invalid",)


def _runtime_profile(row: dict) -> tuple[str, str, tuple[str, ...]]:
    """The requested profile and its source label. A missing key means "auto";
    an out-of-set string resolves to "invalid", which blocks."""
    if "runtime_profile" not in row:
        return "auto", "default.auto", ()
    profile = row.get("runtime_profile")
    if isinstance(profile, str) and profile in _VALID_PROFILES:
        return profile, "registry.runtime_profile", ()
    return "invalid", "registry.runtime_profile", ("invalid_runtime_profile",)


def _runtime_expected_version(row: dict, expected_version: str | None,
                              profile: str) -> tuple[str | None, tuple[str, ...]]:
    """The version the package profile must match; only a "package" profile may
    override the lane's expected version with a pinned "runtime_version"."""
    if profile != "package" or "runtime_version" not in row:
        return expected_version, ()
    return validate_public_version(
        row.get("runtime_version"), "runtime_version_invalid")


def _runtime_python(row: dict) -> tuple[str | None, tuple[str, ...]]:
    """A pinned absolute interpreter path, validated to exist. A relative or
    missing path is a named code, never a silent fallback."""
    value = row.get("runtime_python")
    if value in (None, ""):
        return None, ()
    if not isinstance(value, str):
        return None, ("runtime_python_invalid",)
    path = Path(value).expanduser()
    if not path.is_absolute():
        return None, ("runtime_python_not_absolute",)
    try:
        resolved = path.resolve()
    except OSError:
        return None, ("runtime_python_invalid",)
    return str(resolved), (() if resolved.is_file() else ("runtime_python_missing",))


def _observed_package_version(lane, runtime_python, installed_fn, python_version_fn):
    """The installed version: a pinned interpreter is queried in its own
    environment, else the current interpreter's metadata is read."""
    if runtime_python and lane.kind == "pip":
        return python_version_fn(lane, runtime_python)
    return installed_fn(lane)


def _select_launch(lane, profile, source, python_executable, environ, is_frozen,
                   extra_roots, importable_fn, runtime_python):
    """Choose the one launch to perform, as (launch, selected_runtime,
    bundled_component, bundled_codes). The check order is the precedence: a frozen
    build (lane_runtime_frozen), disabled package, http, bundled, then the profiles."""
    if profile not in _VALID_PROFILES:
        return None, "invalid", None, ()
    if is_frozen:
        return _frozen.select_frozen_launch(lane, profile, python_executable, environ, importable_fn)
    if lane.package_disabled_reason and (profile == "package" or not source):
        return None, "package", None, ()
    if lane.kind == "http":
        return _frozen.select_http_launch(lane, environ)
    if lane.kind == "bundled":
        return (LaunchSpec((python_executable, *lane.mcp_args))
                if lane.command == "python" else LaunchSpec(tuple(lane.mcp_command()))), "bundled", None, ()
    if profile == "source":
        return (_support.source_launch(
            lane, source, python_executable, environ, extra_roots), "source", None, ()) if source else (None, "source", None, ())
    if profile == "package":
        return _support.package_launch(
            lane, python_executable, importable_fn, runtime_python), "package", None, ()
    if source:
        return _support.source_launch(
            lane, source, python_executable, environ, extra_roots), "source", None, ()
    return _support.package_launch(
        lane, python_executable, importable_fn, runtime_python), "package", None, ()


def _blocking_codes(lane, profile, selected, source_available, package_available, mismatch):
    """Decide which accumulated codes make the lane unusable: the mismatch-vs-
    blocking split. Most codes in `mismatch` are advisory and the lane still
    launches (a source version differing from expected is recorded, not fatal). A
    code blocks only when it defeats the selected path: an invalid profile, a
    failed bundled admission, a disabled package, a source profile with no source,
    a package-profile pip/npm lane's bad interpreter, missing package, or mismatch,
    or an "auto" pip/npm package older than its pin (the pin carries the fixes)."""
    if "invalid_runtime_profile" in mismatch:
        return ["invalid_runtime_profile"]
    if selected == "http":
        return [code for code in mismatch if code == "http_endpoint_unset"]
    if selected == "bundled":
        return [code for code in mismatch if _frozen.is_blocking(code)]
    if selected == "package" and lane.package_disabled_reason:
        return ["package_distribution_disabled"]
    if profile == "source" and not source_available:
        return ["source_runtime_missing"]
    if profile == "package" and lane.kind in {"pip", "npm"}:
        codes = [c for c in mismatch if c.startswith("runtime_python_")
                 or c in {"runtime_version_invalid", "installed_version_invalid"}]
        if not package_available:
            codes.append("package_runtime_missing")
        if "installed_version_mismatch" in mismatch:
            codes.append("installed_version_mismatch")
        return codes
    if (selected == "package" and lane.kind in {"pip", "npm"}
            and "installed_version_below_pin" in mismatch):
        return ["installed_version_below_pin"]
    return []

"""Portable lane declarations, source-aware launches, and evidence-led probes."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from . import lane_runtime as _runtime
from .lane_runtime import LaneRuntimeError, ResolvedLaneRuntime
from .lanes_registry import LANES, Lane
from .mcp_client import LaunchSpec

REPO = Path(__file__).resolve().parent.parent
LANE_REGISTRY_PATH = Path(os.environ.get(
    "FLYWHEEL_HOME", str(Path.home() / ".flywheel"))) / "lanes.json"

LIVE = "live"
STALE = "stale"
DECLARED = "declared"
MISSING = "missing"

_importable = _runtime.importable
_frozen = _runtime.frozen
_installed_version = _runtime.installed_version
_package_runtime_version = _runtime.package_runtime_version
_python_import_root = _runtime.python_import_root


def _resolve_repo(source_repo: str) -> Path | None:
    """Resolve one declared source path without embedding a host path in metadata."""
    return _runtime.resolve_repo(source_repo, REPO, os.environ)


def resolve_source_repo(lane: Lane) -> Path | None:
    """Resolve a lane's own declared source path."""
    return _runtime.resolve_source_repo(lane, REPO, os.environ)


def _extra_import_roots(lane: Lane) -> list[str]:
    """Resolved import roots for sibling source repos a lane composes."""
    return _runtime.extra_import_roots(lane, REPO, os.environ)


def _pip_mcp_command(lane: Lane) -> list[str]:
    """Prefer this interpreter for an importable installed Python lane."""
    return _runtime.pip_mcp_command(lane, sys.executable, _importable)


def resolve_mcp_command(name: str) -> list[str]:
    """Return only the portable declared argv used by public roster surfaces."""
    lane = LANES[name]
    return [] if lane.package_disabled_reason else lane.mcp_command()


def resolve_lane_runtime(name: str) -> ResolvedLaneRuntime:
    """Resolve the lane launch and public-safe selected-runtime metadata."""
    return _runtime.resolve_lane_runtime(
        name, LANES, read_registry(), environ=os.environ,
        python_executable=sys.executable, is_frozen=_frozen(),
        source_resolver=resolve_source_repo, extra_roots=_extra_import_roots,
        importable_fn=_importable, installed_version_fn=_installed_version,
        package_runtime_version_fn=_package_runtime_version)


def resolve_mcp_launch(name: str) -> LaunchSpec:
    """Return the selected child launch used only at runtime."""
    return resolve_lane_runtime(name).require_launch()


def lane_status(name: str, *, probe: bool = True, timeout: float = 20.0) -> dict:
    """Health of one lane.

    probe=False reports install/source/runtime-selection metadata only. It does
    not spawn the lane MCP server. probe=True reaches the selected runtime and
    records bounded capability metadata from the tool list.
    """
    lane = LANES.get(name)
    if lane is None:
        return {"name": name, "status": MISSING, "detail": "unknown lane"}
    runtime = resolve_lane_runtime(name)
    if runtime.blocking_codes:
        return _status_row(
            lane, runtime, MISSING,
            f"runtime selection failed: {', '.join(runtime.blocking_codes)}")
    if not runtime.present:
        detail = f"{lane.install_name or name} not installed"
        return _status_row(lane, runtime, MISSING, detail)
    if not probe:
        return _status_row(lane, runtime, DECLARED, _declared_detail(lane, runtime))
    return _probe_lane(
        name, runtime.installed_version, timeout, present=runtime.present,
        runtime=runtime)


def _probe_lane(name: str, installed: str | None, timeout: float, *,
                present: bool, runtime: ResolvedLaneRuntime | None = None) -> dict:
    """Spawn the selected lane MCP server and verify it answers a status tool."""
    from .mcp_client import MCPClient, MCPError
    lane = LANES[name]
    runtime = runtime or resolve_lane_runtime(name)
    try:
        launch = runtime.require_launch()
    except LaneRuntimeError as error:
        return _status_row(
            lane, runtime, MISSING,
            f"runtime selection failed: {', '.join(error.codes)}")
    try:
        with MCPClient(launch, timeout=timeout, client_name="flywheel-lanes") as c:
            tools = c.list_tools()
            names = {t.get("name", "") for t in tools}
            health = next((tn for tn in (
                f"{name}.status", f"{name}.doctor", "status", "doctor",
                f"{name}_status", f"{name}_doctor") if tn in names), None)
            verdict, detail = STALE, f"no status/doctor health tool; {len(tools)} tools"
            if health is not None:
                try:
                    res = c.call_text(health, {})
                    if not res.get("ok"):
                        detail = f"{health} error: health_tool_error (not healthy)"
                    else:
                        verdict, detail = _health_verdict(
                            name, health, res.get("text", ""),
                            getattr(c, "server_info", {}),
                            runtime, len(tools))
                except MCPError:
                    detail = f"{health} error: health_tool_exception"
            return _status_row(
                lane, runtime, verdict, detail, tools=len(tools),
                capability=_runtime.capability_summary(tools))
    except (MCPError, FileNotFoundError, OSError) as error:
        return _status_row(
            lane, runtime, DECLARED if present else MISSING,
            f"MCP probe failed: {_probe_failure_code(error)} (cannot launch)")


def _status_row(lane: Lane, runtime: ResolvedLaneRuntime, status: str,
                detail: str, *, tools: int | None = None,
                capability: dict | None = None) -> dict:
    if "package_distribution_disabled" in runtime.blocking_codes:
        detail = f"{detail}. {lane.package_disabled_reason}"
    row = {
        "name": lane.name, "kind": lane.kind,
        "package_installable": lane.kind in {"pip", "npm"} and not lane.package_disabled_reason,
        "installed_version": runtime.installed_version,
        "expected_version": runtime.expected_version, "status": status,
        "organ": lane.organ, "role": lane.role, "detail": detail,
        "resolved_runtime": runtime.to_dict(capability),
    }
    if tools is not None:
        row["tools"] = tools
    return row


def _declared_detail(lane: Lane, runtime: ResolvedLaneRuntime) -> str:
    if lane.kind == "http":
        return lane.endpoint_detail()
    return f"{runtime.selected_runtime} runtime selected; not MCP-probed"


def _health_verdict(
        name: str, health: str, text: str, server_info: dict,
        runtime: ResolvedLaneRuntime, tool_count: int) -> tuple[str, str]:
    if name == "relay":
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return STALE, f"{health} answered invalid JSON"
        if not isinstance(payload, dict):
            return STALE, f"{health} answered invalid JSON"
        expected = runtime.expected_version
        if payload.get("ok") is not True:
            return STALE, f"{health} answered but Relay is not healthy"
        if payload.get("server") != "relay":
            return STALE, f"{health} answered with wrong Relay identity"
        if expected and payload.get("version") != expected:
            return STALE, f"{health} answered with wrong Relay version"
        if expected and server_info.get("version") != expected:
            return STALE, f"{health} serverInfo version mismatch"
        return LIVE, f"{health} answered Relay {expected}; {tool_count} tools"
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return LIVE, f"{health} answered; {tool_count} tools"
    if isinstance(payload, dict) and payload.get("ok") is False:
        return STALE, f"{health} answered but reported not healthy"
    return LIVE, f"{health} answered; {tool_count} tools"


def _probe_failure_code(error: BaseException) -> str:
    if isinstance(error, FileNotFoundError):
        return "runtime_executable_missing"
    return "mcp_probe_failed"


def lane_roster(*, probe: bool = False, timeout: float = 20.0) -> dict:
    """Health for every lane. probe=True performs live MCP handshakes."""
    rows = [lane_status(name, probe=probe, timeout=timeout) for name in LANES]
    by: dict[str, int] = {row["status"]: 0 for row in rows}
    for row in rows:
        by[row["status"]] = by.get(row["status"], 0) + 1
    return {
        "schema": "flywheel.lanes/v1",
        "n_lanes": len(rows),
        "by_status": by,
        "all_live": by.get(LIVE, 0) == len(rows),
        "lanes": rows,
        "note": ("probe=True reaches each lane's MCP server for a live handshake; "
                 "probe=False checks install/source/runtime selection only.")
        if probe else
        "install-presence roster; pass probe=True for a live MCP health check.",
    }


def lane_report(roster: dict | None = None, *, probe: bool = False) -> str:
    """Human-readable lane roster."""
    roster = roster or lane_roster(probe=probe)
    lines = [f"Flywheel lanes -- {roster['n_lanes']} lanes; "
             f"live {roster['by_status'].get(LIVE, 0)}, "
             f"declared {roster['by_status'].get(DECLARED, 0)}, "
             f"missing {roster['by_status'].get(MISSING, 0)}",
             roster.get("note", "")]
    for row in roster["lanes"]:
        lines.append(f"  {row['name']:13} [{row['status']:8}] "
                     f"{row.get('organ', ''):14} {row.get('detail', '')}")
    return "\n".join(lines)


def install_lane(name: str, *, profile: str = "package") -> dict:
    """Install one lane. profile='package' uses pip/npm; 'source' uses editable."""
    lane = LANES.get(name)
    if lane is None:
        return {"name": name, "installed": False, "detail": "unknown lane"}
    if lane.kind in ("bundled", "http"):
        return {"name": name, "installed": True,
                "detail": f"{lane.kind} lane (no install needed)"}
    if profile != "source" and lane.package_disabled_reason:
        return {"name": name, "installed": False,
                "code": "package_distribution_disabled",
                "detail": lane.package_disabled_reason}
    try:
        if profile == "source":
            repo = resolve_source_repo(lane)
            if repo is None:
                return {"name": name, "installed": False,
                        "detail": f"source checkout not found: {lane.source_repo}"}
        if lane.kind == "pip":
            cmd = ["pip", "install", "-e", str(repo)] if profile == "source" else [
                "pip", "install", lane.install_name]
        elif lane.kind == "npm":
            cmd = ["npm", "install", "-g", str(repo)] if profile == "source" else [
                "npm", "install", "-g", lane.install_name]
        else:
            return {"name": name, "installed": False,
                    "detail": f"unknown kind {lane.kind}"}
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        ok = result.returncode == 0
        return {"name": name, "installed": ok, "cmd": cmd,
                "detail": (result.stdout[-200:] if ok else
                           (result.stderr[-300:] or result.stdout[-300:])).strip()}
    except (FileNotFoundError, subprocess.TimeoutExpired) as error:
        return {"name": name, "installed": False, "detail": f"install failed: {error}"}


def write_registry(installed: dict) -> None:
    """Record the installed lane registry to FLYWHEEL_HOME/lanes.json."""
    LANE_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    LANE_REGISTRY_PATH.write_text(
        json.dumps(installed, indent=2, sort_keys=True), encoding="utf-8")


def read_registry() -> dict:
    """Load the lane registry, or empty dict if absent."""
    try:
        return json.loads(LANE_REGISTRY_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


if __name__ == "__main__":
    print(lane_report())

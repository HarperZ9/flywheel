"""Portable lane declarations, source-aware launches, and evidence-led probes."""
from __future__ import annotations

import functools
import importlib.metadata
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

from .lanes_registry import LANES, Lane
from .mcp_client import LaunchSpec

REPO = Path(__file__).resolve().parent.parent
# Where the lane registry (installed versions + profiles) is recorded.
LANE_REGISTRY_PATH = Path(os.environ.get("FLYWHEEL_HOME", str(Path.home() / ".flywheel"))) / "lanes.json"

# Statuses a lane can report.
LIVE = "live"
STALE = "stale"
DECLARED = "declared"
MISSING = "missing"


def _resolve_repo(source_repo: str) -> Path | None:
    """Resolve one declared source path without embedding a host path in metadata."""
    source = Path(source_repo)
    if not source_repo:
        return None
    candidates = []
    explicit = os.environ.get("FLYWHEEL_WORKSPACE_ROOT", "").strip()
    if explicit:
        candidates.append(Path(explicit).expanduser() / source)
    candidates.append(REPO.parent / source)
    if source.parts and REPO.parent.name == source.parts[0]:
        candidates.append(REPO.parent.joinpath(*source.parts[1:]))
    seen = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved not in seen and resolved.is_dir():
            return resolved
        seen.add(resolved)
    return None


def resolve_source_repo(lane: Lane) -> Path | None:
    """Resolve a lane's own declared source path."""
    return _resolve_repo(lane.source_repo)


def _extra_import_roots(lane: Lane) -> list:
    """The /src import root of each sibling repo a lane composes at runtime, so a
    lane importing uninstalled siblings (e.g. accountable-surface -> coherence-membrane
    + proof-surface) still imports and probes live."""
    roots = []
    for spec in getattr(lane, "extra_source_repos", ()) or ():
        repo = _resolve_repo(spec)
        if repo is None:
            continue
        src = repo / "src"
        roots.append(str((src if src.is_dir() else repo).resolve()))
    return roots


def _importable(top_module: str) -> bool:
    """True when `top_module` imports in THIS interpreter. Seam for tests."""
    try:
        return importlib.util.find_spec(top_module) is not None
    except (ImportError, ValueError):
        return False


def _frozen() -> bool:
    """True when sys.executable is a frozen gateway, not a Python interpreter."""
    return bool(getattr(sys, "frozen", False))


def _pip_mcp_command(lane: Lane) -> list[str]:
    """Prefer this interpreter for an importable installed Python lane."""
    if lane.py_module and not _frozen():
        top = lane.py_module.split(".", 1)[0]
        if _importable(top):
            return [sys.executable, "-m", lane.py_module, *lane.mcp_args]
    return lane.mcp_command()


def _python_import_root(source: Path, lane: Lane) -> Path:
    top = lane.py_module.split(".", 1)[0]
    for root in (source / "src", source):
        if (root / top).is_dir() or (root / f"{top}.py").is_file():
            return root.resolve()
    return source.resolve()


def resolve_mcp_command(name: str) -> list[str]:
    """Return only the portable declared argv used by public roster surfaces."""
    return LANES[name].mcp_command()


def resolve_mcp_launch(name: str) -> LaunchSpec:
    """Return the source/package-aware child launch used only at runtime."""
    lane = LANES[name]
    if _frozen():
        return LaunchSpec(tuple(lane.mcp_command()))
    source = resolve_source_repo(lane)
    if source and lane.kind == "npm":
        return LaunchSpec(("node", str((source / lane.mcp_args[0]).resolve())))
    if lane.kind == "pip":
        if source and lane.py_module:
            import_root = _python_import_root(source, lane)
            inherited = os.environ.get("PYTHONPATH", "")
            # the lane's own import root stays FIRST (so its package wins), then any
            # sibling roots it composes, then the inherited path.
            roots = [str(import_root), *_extra_import_roots(lane)]
            if inherited:
                roots.append(inherited)
            pythonpath = os.pathsep.join(roots)
            return LaunchSpec(
                (sys.executable, "-m", lane.py_module, *lane.mcp_args), str(source),
                (("PYTHONPATH", pythonpath), ("PYTHONSAFEPATH", "1")))
        return LaunchSpec(tuple(_pip_mcp_command(lane)))
    if lane.command == "python" and not _frozen():
        return LaunchSpec((sys.executable, *lane.mcp_args))
    return LaunchSpec(tuple(lane.mcp_command()))


@functools.lru_cache(maxsize=1)
def _npm_global_root() -> Path | None:
    """Global npm module root, resolved once per process; None when npm is absent.

    Reading each lane's package.json under this root is a filesystem read, so
    the whole npm side of the roster costs one `npm root -g` spawn instead of
    one `npm ls -g` spawn per lane.
    """
    try:
        npm = "npm.cmd" if os.name == "nt" else "npm"
        r = subprocess.run(
            [npm, "root", "-g"], capture_output=True, text=True, timeout=20)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    line = r.stdout.strip()
    return Path(line) if line else None


def _installed_version(lane: Lane) -> str | None:
    """Best-effort installed version; presence-only and credential-free.

    Resolved in-process: importlib.metadata for pip lanes and one cached global
    npm root for npm lanes. Both read the same install metadata the old
    subprocess path read, so lane detection is unchanged; only the per-lane
    process spawn is gone. Spawning `pip show` per lane cost ~2s each and pushed
    /api/desktop/status past the desktop client's probe timeout, so a paired
    device read the engine as offline while the socket was in fact connecting.
    """
    try:
        if lane.kind == "bundled":
            return lane.version
        if lane.kind == "pip":
            try:
                return importlib.metadata.version(lane.install_name)
            except importlib.metadata.PackageNotFoundError:
                return None
        if lane.kind == "npm":
            root = _npm_global_root()
            if root is None:
                return None
            manifest = root / lane.install_name / "package.json"
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None
            version = data.get("version")
            return version if isinstance(version, str) else None
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return None
    return None


def lane_status(name: str, *, probe: bool = True, timeout: float = 20.0) -> dict:
    """Health of one lane. probe=True spawns the MCP server and calls its status tool.

    Returns {name, kind, installed_version, expected_version, status, detail}.
    `probe=False` skips the MCP handshake (filesystem/install check only) and
    is the right mode for a quick roster or an untrusted caller.
    """
    lane = LANES.get(name)
    if lane is None:
        return {"name": name, "status": MISSING, "detail": "unknown lane"}
    installed = _installed_version(lane)
    source = resolve_source_repo(lane)
    present = installed is not None or source is not None or lane.kind == "bundled"
    if not present:
        return {"name": name, "kind": lane.kind, "installed_version": None,
                "expected_version": lane.version, "status": MISSING,
                "organ": lane.organ, "role": lane.role,
                "detail": f"{lane.install_name} not installed"}
    if not probe:
        return {"name": name, "kind": lane.kind, "installed_version": installed,
                "expected_version": lane.version, "status": DECLARED,
                "organ": lane.organ, "role": lane.role,
                "detail": ((f"source checkout at {lane.source_repo}; "
                            "not MCP-probed") if source and installed is None else
                           "install-presence verified; not MCP-probed")}
    return _probe_lane(name, installed, timeout, present=present)


def _probe_lane(name: str, installed: str | None, timeout: float, *,
                present: bool) -> dict:
    """Spawn the lane's MCP server and verify it answers a status tool."""
    from .mcp_client import MCPClient, MCPError
    lane = LANES[name]
    launch = resolve_mcp_launch(name)
    try:
        with MCPClient(launch, timeout=timeout, client_name="flywheel-lanes") as c:
            tools = c.list_tools()
            tool_names = {t.get("name", "") for t in tools}
            status_tool = next(
                (tn for tn in (
                    f"{name}.status", f"{name}.doctor", "status", "doctor",
                    f"{name}_status", f"{name}_doctor") if tn in tool_names),
                None)
            verdict, detail = STALE, f"no status/doctor health tool; {len(tools)} tools"
            if status_tool is not None:
                try:
                    res = c.call_text(status_tool, {})
                    if res.get("ok"):
                        verdict, detail = LIVE, f"{status_tool} answered; {len(tools)} tools"
                    else:
                        detail = f"{status_tool} error: {res.get('text', '')[:200]}"
                except MCPError as e:
                    detail = f"{status_tool} error: {e}"
            return {"name": name, "kind": lane.kind, "installed_version": installed,
                    "expected_version": lane.version, "status": verdict,
                    "organ": lane.organ, "role": lane.role,
                    "tools": len(tools), "detail": detail}
    except (MCPError, FileNotFoundError, OSError) as e:
        return {"name": name, "kind": lane.kind, "installed_version": installed,
                "expected_version": lane.version, "status": DECLARED if present else MISSING,
                "organ": lane.organ, "role": lane.role,
                "detail": f"MCP probe failed: {e}"}


def lane_roster(*, probe: bool = False, timeout: float = 20.0) -> dict:
    """Health for every lane. probe=False by default (fast, install-only);
    probe=True spawns each MCP server for a live handshake (slower)."""
    rows = [lane_status(name, probe=probe, timeout=timeout) for name in LANES]
    by = {r["status"]: 0 for r in rows}
    for r in rows:
        by[r["status"]] = by.get(r["status"], 0) + 1
    return {
        "schema": "flywheel.lanes/v1",
        "n_lanes": len(rows),
        "by_status": by,
        "all_live": by.get(LIVE, 0) == len(rows),
        "lanes": rows,
        "note": ("probe=True spawns each lane's MCP server for a live handshake; "
                 "probe=False checks install presence only.") if probe else
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
    for r in roster["lanes"]:
        lines.append(f"  {r['name']:13} [{r['status']:8}] {r.get('organ', ''):14} "
                     f"{r.get('detail', '')}")
    return "\n".join(lines)


def install_lane(name: str, *, profile: str = "package") -> dict:
    """Install one lane. profile='package' uses pip/npm; 'source' uses the
    in-repo checkout (editable). Returns a result dict; never raises on a
    missing tool (reports it)."""
    lane = LANES.get(name)
    if lane is None:
        return {"name": name, "installed": False, "detail": "unknown lane"}
    if lane.kind == "bundled":
        return {"name": name, "installed": True, "detail": "bundled lane (no install needed)"}
    try:
        if profile == "source":
            repo = resolve_source_repo(lane)
            if repo is None:
                return {"name": name, "installed": False,
                        "detail": f"source checkout not found: {lane.source_repo}"}
        if lane.kind == "pip":
            if profile == "source":
                cmd = ["pip", "install", "-e", str(repo)]
            else:
                cmd = ["pip", "install", lane.install_name]
        elif lane.kind == "npm":
            if profile == "source":
                cmd = ["npm", "install", "-g", str(repo)]
            else:
                cmd = ["npm", "install", "-g", lane.install_name]
        else:
            return {"name": name, "installed": False, "detail": f"unknown kind {lane.kind}"}
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        ok = r.returncode == 0
        return {"name": name, "installed": ok, "cmd": cmd,
                "detail": (r.stdout[-200:] if ok else (r.stderr[-300:] or r.stdout[-300:])).strip()}
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return {"name": name, "installed": False, "detail": f"install failed: {e}"}


def write_registry(installed: dict) -> None:
    """Record the installed lane registry to FLYWHEEL_HOME/lanes.json."""
    LANE_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    LANE_REGISTRY_PATH.write_text(json.dumps(installed, indent=2, sort_keys=True), encoding="utf-8")


def read_registry() -> dict:
    """Load the lane registry, or empty dict if absent."""
    try:
        return json.loads(LANE_REGISTRY_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


if __name__ == "__main__":
    print(lane_report())

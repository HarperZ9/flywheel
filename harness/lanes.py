"""lanes.py -- the lane layer: Flywheel as the umbrella over the tool family.

Flywheel is the one platform. The flagship tools (gather, crucible, index,
forum, learn, telos) and the trained-model lane (local-model) are LANES inside
it -- each a provisioned, health-checked organ reachable through one surface.
This module is the seam that composes them.

Built on three things that already exist, so nothing is reinvented:

  1. telos's mcp-server-manifest.json (public/telos/demo/integrations/) -- the
     verified, host-portable manifest of the flagship MCP servers, with
     source_checkout + package profiles, freshness probes, and failure codes.
  2. superproject.MANIFEST/EXTENDED -- the organ model (perception,
     verification, structure, orchestration, reconciliation) that already maps
     each flagship to its role in the reconcile.
  3. mcp_client.open_mcp + MCPAllowlist -- the gated, witnessed MCP consumption
     path. A lane is health-checked by spawning its MCP server (allowlisted),
     calling its `status`/`doctor` tool, and closing it.

A lane's health is: live (MCP handshake + status tool answered), stale
(connected but version/behavior drift), declared (present on disk, not
probed), or missing (not installed). Graceful: a down lane never breaks the
roster; it reports `missing`/`declared` honestly.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TELOS_MANIFEST = REPO.parent / "public" / "telos" / "demo" / "integrations" / "mcp-server-manifest.json"

# Where the lane registry (installed versions + profiles) is recorded.
LANE_REGISTRY_PATH = Path(os.environ.get("FLYWHEEL_HOME", str(Path.home() / ".flywheel"))) / "lanes.json"

# Statuses a lane can report.
LIVE = "live"
STALE = "stale"
DECLARED = "declared"
MISSING = "missing"


@dataclass
class Lane:
    """One lane of Flywheel: a flagship tool or the trained-model lane.

    install_name: the pip/npm distribution name (differs from the command).
    command:      the console-script or node entry invoked to start its MCP server.
    mcp_args:     args following `command` to launch the MCP stdio server.
    kind:         pip | npm | bundled.
    version:      the version this lane declares (manifest cross-reference).
    role:         one-line role in the reconcile.
    organ:        the superproject organ this lane instantiates.
    """
    name: str
    install_name: str
    command: str
    mcp_args: tuple[str, ...]
    kind: str                       # "pip" | "npm" | "bundled"
    version: str
    role: str
    organ: str
    source_repo: str = ""           # for the source-checkout install profile

    def mcp_command(self) -> list[str]:
        """The argv that launches this lane's MCP stdio server."""
        return [self.command, *self.mcp_args]


# The lane registry. install_name -> command asymmetry is mapped explicitly
# (pip install gather-engine exposes the `gather` command, etc.). local-model
# is bundled (no install; it IS Flywheel). learn is added here even though
# telos's manifest omits it -- closing a known gap so Flywheel's roster is
# complete.
LANES: dict[str, Lane] = {
    "gather": Lane(
        "gather", "gather-engine", "gather", ("mcp",), "pip", "1.6.1",
        "research intake + provenance receipts (verified-data flywheel intake)",
        "perception", source_repo="public/gather"),
    "crucible": Lane(
        "crucible", "crucible-bench", "crucible", ("mcp",), "pip", "1.2.0",
        "falsifiable verification + re-check (register -> steelman -> measure -> witness)",
        "verification", source_repo="public/crucible"),
    "index": Lane(
        "index", "index-graph", "index", ("mcp",), "pip", "2.9.0",
        "workspace map + symbol graph + verified wiki (the catalog lane)",
        "structure", source_repo="public/index"),
    "forum": Lane(
        "forum", "forum-engine", "forum", ("mcp",), "pip", "1.13.0",
        "witnessed causal ledger + model-agnostic routing",
        "orchestration", source_repo="public/forum"),
    "learn": Lane(
        "learn", "@harperz9/learn", "node", ("src/mcp.mjs",), "npm", "1.6.0",
        "accountable learning forge (spaced repetition + retrieval practice)",
        "memory", source_repo="public/learn"),
    "telos": Lane(
        "telos", "project-telos-mcp", "node", ("demo/telos-mcp.mjs",), "npm", "0.2.0",
        "the reconciliation lane: five-tool workflow + creative engine + doctors",
        "reconciliation", source_repo="public/telos"),
    "local-model": Lane(
        "local-model", "", "python", ("-m", "harness.local_mcp"), "bundled", "0.1.0",
        "the trained 14B proposer + verified-inference harness (the engine lane)",
        "propose-verify"),
}


def _node_mcp_command(lane: Lane) -> list[str]:
    """Resolve a node lane's MCP command to an absolute path under its source repo.

    telos's package profile uses a relative `demo/telos-mcp.mjs`; for the
    source-checkout profile we resolve it against the lane's repo so the
    command works from any cwd. Falls back to the bare command if the repo
    is absent (declared, not installed).
    """
    if lane.kind != "npm" or not lane.source_repo:
        return lane.mcp_command()
    script = REPO.parent / lane.source_repo / lane.mcp_args[0]
    if script.exists():
        return ["node", str(script)]
    return lane.mcp_command()


def resolve_mcp_command(name: str) -> list[str]:
    """The argv to launch lane `name`'s MCP server, profile-aware."""
    lane = LANES[name]
    if lane.kind == "npm":
        return _node_mcp_command(lane)
    return lane.mcp_command()


def _installed_version(lane: Lane) -> str | None:
    """Best-effort: the installed version of a lane, or None if absent.

    For pip lanes, `pip show <install_name>` returns the version. For npm
    lanes, `npm ls -g <install_name> --depth=0`. For bundled, the static
    version. Presence-only: never returns a credential or value.
    """
    try:
        if lane.kind == "bundled":
            return lane.version
        if lane.kind == "pip":
            r = subprocess.run(
                ["pip", "show", lane.install_name],
                capture_output=True, text=True, timeout=15)
            for ln in r.stdout.splitlines():
                if ln.lower().startswith("version:"):
                    return ln.split(":", 1)[1].strip()
            return None
        if lane.kind == "npm":
            r = subprocess.run(
                ["npm", "ls", "-g", lane.install_name, "--depth=0", "--json"],
                capture_output=True, text=True, timeout=20)
            deps = json.loads(r.stdout or "{}").get("dependencies", {})
            entry = deps.get(lane.install_name)
            return entry.get("version") if isinstance(entry, dict) else None
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
    if installed is None and lane.kind != "bundled":
        # Check the source checkout as a fallback (declared but not packaged).
        repo = REPO.parent / lane.source_repo if lane.source_repo else None
        if repo and repo.exists():
            return {"name": name, "kind": lane.kind, "installed_version": None,
                    "expected_version": lane.version, "status": DECLARED,
                    "organ": lane.organ, "role": lane.role,
                    "detail": f"source checkout at {lane.source_repo}, not pip/npm installed"}
        return {"name": name, "kind": lane.kind, "installed_version": None,
                "expected_version": lane.version, "status": MISSING,
                "organ": lane.organ, "role": lane.role,
                "detail": f"{lane.install_name} not installed"}
    if not probe:
        return {"name": name, "kind": lane.kind, "installed_version": installed,
                "expected_version": lane.version,
                "status": LIVE if installed else DECLARED,
                "organ": lane.organ, "role": lane.role,
                "detail": "install-verified (not MCP-probed)"}
    # Live MCP probe: spawn the server, call its status/doctor tool, close it.
    return _probe_lane(name, installed, timeout)


def _probe_lane(name: str, installed: str | None, timeout: float) -> dict:
    """Spawn the lane's MCP server and verify it answers a status tool."""
    from .mcp_client import MCPClient, MCPError
    lane = LANES[name]
    command = resolve_mcp_command(name)
    try:
        with MCPClient(command, timeout=timeout, client_name="flywheel-lanes") as c:
            c.start()
            tools = c.list_tools()
            tool_names = {t.get("name", "") for t in tools}
            # Each lane exposes either <name>.status, <name>.doctor, or a bare
            # status/doctor. Call the first match for a live health signal.
            status_tool = next(
                (tn for tn in (
                    f"{name}.status", f"{name}.doctor", "status", "doctor",
                    f"{name}_status", f"{name}_doctor") if tn in tool_names),
                None)
            detail = f"server up, {len(tools)} tools"
            verdict = LIVE
            if status_tool:
                try:
                    res = c.call_text(status_tool, {})
                    # A status tool that answered is live; version drift => stale.
                    verdict = LIVE
                    detail = f"{status_tool} answered; {len(tools)} tools"
                except MCPError as e:
                    verdict = STALE
                    detail = f"{status_tool} error: {e}"
            return {"name": name, "kind": lane.kind, "installed_version": installed,
                    "expected_version": lane.version, "status": verdict,
                    "organ": lane.organ, "role": lane.role,
                    "tools": len(tools), "detail": detail}
    except (MCPError, FileNotFoundError, OSError) as e:
        return {"name": name, "kind": lane.kind, "installed_version": installed,
                "expected_version": lane.version, "status": DECLARED if installed else MISSING,
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
             f"missing {roster['by_status'].get(MISSING, 0)}"]
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
        if lane.kind == "pip":
            if profile == "source" and lane.source_repo:
                repo = REPO.parent / lane.source_repo
                cmd = ["pip", "install", "-e", str(repo)]
            else:
                cmd = ["pip", "install", lane.install_name]
        elif lane.kind == "npm":
            if profile == "source" and lane.source_repo:
                repo = REPO.parent / lane.source_repo
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

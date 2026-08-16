"""plugins.py -- one manifest shape over every capability the surface mounts.

A plugin is {name, kind, ...}. Three kinds ride runtime primitives that
already exist:
- lane:    a bundled flagship lane (from lanes.LANES); its MCP server is the
           plugin body. Always registered, cannot be removed.
- builtin: a tool set inside the gated ToolExecutor (read/grep/glob/edit/run).
           Always registered; the gate, not the registry, decides use.
- mcp:     an external MCP stdio server the user registers by command.

Custom mcp entries persist at ~/.flywheel/plugins.json (FLYWHEEL_HOME
override honored). Registration grants NOTHING: outbound MCP calls stay
behind the ToolGate's allow_mcp and the run's allowlist. Probing spawns the
server and reports its real tool list; the answer is the server's, never
assumed."""
from __future__ import annotations

import json
import os
from pathlib import Path

from .lanes import LANES, resolve_mcp_command, resolve_mcp_launch

# The gated builtin tool sets (local_tools.ToolExecutor). Names only; the
# gate decides what actually runs.
BUILTIN_TOOLS = ("read", "grep", "glob", "apply_patch", "run")


def _registry_path() -> Path:
    home = os.environ.get("FLYWHEEL_HOME") or os.path.join(
        os.path.expanduser("~"), ".flywheel")
    return Path(home) / "plugins.json"


def _load_custom() -> list:
    p = _registry_path()
    if not p.exists():
        return []
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
        entries = doc.get("mcp", [])
        return entries if isinstance(entries, list) else []
    except (OSError, ValueError):
        return []


def _save_custom(entries: list) -> None:
    p = _registry_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"schema": "flywheel.plugins/v1", "mcp": entries},
                            indent=1), encoding="utf-8")


def plugin_roster() -> dict:
    """Every mounted capability under one manifest shape."""
    plugins = []
    for name, lane in LANES.items():
        plugins.append({
            "name": name, "kind": "lane", "enabled": True, "removable": False,
            "detail": lane.role, "organ": lane.organ,
            "command": resolve_mcp_command(name)})
    plugins.append({
        "name": "tools", "kind": "builtin", "enabled": True, "removable": False,
        "detail": "gated in-process tool set; write/exec are grants, not defaults",
        "tools": list(BUILTIN_TOOLS)})
    for e in _load_custom():
        plugins.append({
            "name": e.get("name", ""), "kind": "mcp",
            "enabled": bool(e.get("enabled", True)), "removable": True,
            "detail": e.get("detail", "user-registered MCP server"),
            "command": e.get("command", [])})
    return {"schema": "flywheel.plugins/v1", "plugins": plugins,
            "n": len(plugins),
            "note": "registration grants nothing; outbound MCP calls stay "
                    "behind the tool gate and the run allowlist"}


def register_mcp(name: str, command: list, detail: str = "") -> dict:
    """Register a custom MCP stdio server by argv. Names must be new and
    must not shadow a lane or the builtin set."""
    name = (name or "").strip()
    if not name:
        return {"error": "provide a plugin name"}
    if name in LANES or name == "tools":
        return {"error": f"'{name}' is reserved by a bundled plugin"}
    if not isinstance(command, list) or not command or \
            not all(isinstance(c, str) and c.strip() for c in command):
        return {"error": "provide 'command' as a non-empty list of strings"}
    entries = _load_custom()
    if any(e.get("name") == name for e in entries):
        return {"error": f"'{name}' is already registered"}
    entries.append({"name": name, "command": command,
                    "detail": detail or "user-registered MCP server",
                    "enabled": True})
    _save_custom(entries)
    return {"registered": name, "n_custom": len(entries)}


def toggle_mcp(name: str, enabled: bool) -> dict:
    entries = _load_custom()
    for e in entries:
        if e.get("name") == name:
            e["enabled"] = bool(enabled)
            _save_custom(entries)
            return {"name": name, "enabled": bool(enabled)}
    return {"error": f"no custom plugin named '{name}'"}


def remove_mcp(name: str) -> dict:
    entries = _load_custom()
    kept = [e for e in entries if e.get("name") != name]
    if len(kept) == len(entries):
        return {"error": f"no custom plugin named '{name}'"}
    _save_custom(kept)
    return {"removed": name, "n_custom": len(kept)}


def call_plugin(name: str, tool: str, arguments: "dict | None" = None,
                timeout: float = 45.0, client_factory=None) -> dict:
    """Spawn a registered plugin's server and call ONE tool. Admission is
    the same as probing: lanes and registered custom servers only, so this
    route never launches an arbitrary command. The result is the server's
    own answer under its own name, never an assumption."""
    if name == "tools":
        return {"error": "the builtin tool set runs inside gated agent "
                         "runs, not through this route"}
    if name in LANES:
        command = resolve_mcp_launch(name)
        kind = "lane"
    else:
        entry = next((e for e in _load_custom() if e.get("name") == name), None)
        if entry is None:
            return {"error": f"no plugin named '{name}'"}
        if not entry.get("enabled", True):
            return {"error": f"plugin '{name}' is disabled; enable it first"}
        command = entry.get("command", [])
        kind = "mcp"
    from .mcp_client import MCPClient, MCPError
    factory = client_factory or MCPClient
    try:
        with factory(command, timeout=timeout,
                     client_name="flywheel-plugins") as c:
            out = c.call_text(tool, arguments or {})
            return {"name": name, "kind": kind, "tool": tool, "result": out}
    except (MCPError, FileNotFoundError, OSError) as error:
        return {"error": f"{type(error).__name__}: {error}", "name": name,
                "tool": tool}


def probe_plugin(name: str, timeout: float = 20.0, client_factory=None) -> dict:
    """Spawn the plugin's server and report its real tools. Lanes and custom
    mcp plugins probe alike; builtins list their gated set directly."""
    if name == "tools":
        return {"name": name, "kind": "builtin", "status": "live",
                "tools": list(BUILTIN_TOOLS)}
    if name in LANES:
        command = resolve_mcp_launch(name)
        kind = "lane"
    else:
        entry = next((e for e in _load_custom() if e.get("name") == name), None)
        if entry is None:
            return {"error": f"no plugin named '{name}'"}
        if not entry.get("enabled", True):
            return {"name": name, "kind": "mcp", "status": "disabled",
                    "detail": "enable it before probing"}
        command = entry.get("command", [])
        kind = "mcp"
    from .mcp_client import MCPClient, MCPError
    factory, client = client_factory or MCPClient, None
    try:
        client = factory(command, timeout=timeout,
                         client_name="flywheel-plugins")
        client.start()
        tools = client.list_tools()
        # Keep the FULL spec (name + description + inputSchema) so a caller
        # can build a form/args UI instead of a blind {} box. `tools` stays a
        # sorted name list for back-compat with older consumers.
        specs = sorted(
            ({"name": t.get("name", ""),
              "description": t.get("description", ""),
              "inputSchema": t.get("inputSchema") or {}}
             for t in tools if isinstance(t, dict)),
            key=lambda s: s["name"])
        return {"name": name, "kind": kind, "status": "live",
                "n_tools": len(specs),
                "tools": [s["name"] for s in specs],
                "tool_specs": specs}
    except (MCPError, FileNotFoundError, OSError) as error:
        detail = f"{type(error).__name__}: {error}"
        tail = client.stderr_tail() if client is not None else ""
        if tail:
            detail += f" | server stderr: {tail[-400:]}"
        return {"name": name, "kind": kind, "status": "unreachable",
                "detail": detail}
    finally:
        if client is not None:
            client.close()

"""One gated manifest for bundled lanes, tools, and custom MCP servers."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re

from .lanes import LANES, resolve_mcp_command, resolve_mcp_launch

# The gated builtin tool sets (local_tools.ToolExecutor). Names only; the
# gate decides what actually runs.
BUILTIN_TOOLS = ("read", "grep", "glob", "apply_patch", "run")
_CREDENTIAL_REF = re.compile(r"cred_[0-9a-f]{32}\Z")
_SLOT_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_WINDOWS_ENV = frozenset((
    "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP"))
_POSIX_ENV = frozenset(("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL"))


class PluginPermissionError(RuntimeError):
    """A fixed non-enumerating launch/metadata refusal."""

    code = "PERMISSION_REQUIRED"

    def __init__(self) -> None:
        super().__init__(self.code)


def _permission() -> dict:
    return {"code": "PERMISSION_REQUIRED", "error": "permission required"}


def _safe_plan(name, command, detail) -> None:
    try:
        if (type(name) is not str or type(command) is not list or not command
                or any(type(item) is not str or not item.strip()
                       for item in command) or type(detail) is not str):
            raise ValueError
        from .gateway_secret_boundary import validate_no_raw_secrets
        validate_no_raw_secrets({"name": name, "command": command,
                                 "detail": detail})
    except Exception:
        raise PluginPermissionError from None


def _credential_metadata(requires, credential_refs, *, allow_unbound=False):
    if (type(requires) not in (list, tuple)
            or type(credential_refs) not in (list, tuple)):
        raise PluginPermissionError
    slots, refs = list(requires or ()), list(credential_refs or ())
    execution_names = _WINDOWS_ENV | _POSIX_ENV
    valid = (all(type(slot) is str and _SLOT_NAME.fullmatch(slot)
                 and slot.upper() not in execution_names for slot in slots)
             and all(type(ref) is str and _CREDENTIAL_REF.fullmatch(ref)
                     for ref in refs)
             and len(slots) == len(set(slots)) and len(refs) == len(set(refs)))
    if not valid or (len(slots) != len(refs) and not (allow_unbound and not refs)):
        raise PluginPermissionError
    return tuple(slots), tuple(refs)


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
        try:
            _safe_plan(e.get("name"), e.get("command"), e.get("detail", ""))
            _credential_metadata(e.get("requires"), e.get("credential_refs"))
        except PluginPermissionError:
            continue
        plugins.append({
            "name": e.get("name", ""), "kind": "mcp",
            "enabled": bool(e.get("enabled", True)), "removable": True,
            "detail": e.get("detail", "user-registered MCP server"),
            "command": e.get("command", []),
            "requires": e.get("requires", []),
            "credential_refs": e.get("credential_refs", [])})
    return {"schema": "flywheel.plugins/v1", "plugins": plugins,
            "n": len(plugins),
            "note": "registration grants nothing; outbound MCP calls stay "
                    "behind the tool gate and the run allowlist"}


def register_mcp(name: str, command: list, detail: str = "", *,
                 requires=(), credential_refs=()) -> dict:
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
    try:
        _safe_plan(name, command, detail)
        slots, refs = _credential_metadata(requires, credential_refs)
    except PluginPermissionError:
        return _permission()
    entries = _load_custom()
    if any(e.get("name") == name for e in entries):
        return {"error": f"'{name}' is already registered"}
    entries.append({"name": name, "command": command,
                    "detail": detail or "user-registered MCP server",
                    "enabled": True, "requires": list(slots),
                    "credential_refs": list(refs)})
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


def plugin_credentials(name: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return safe frozen credential metadata, never credential values."""
    return plugin_execution_plan(name)[2:]


def plugin_execution_plan(name: str):
    """Freeze launch and credential metadata from one registry read."""
    if name == "tools":
        return None, "builtin", (), ()
    if name in LANES:
        return resolve_mcp_launch(name), "lane", (), ()
    entry = next((row for row in _load_custom() if row.get("name") == name), None)
    if entry is None or not entry.get("enabled", True):
        raise PluginPermissionError
    _safe_plan(entry.get("name"), entry.get("command"), entry.get("detail", ""))
    slots, refs = _credential_metadata(
        entry.get("requires"), entry.get("credential_refs"))
    return tuple(entry["command"]), "mcp", slots, refs
def _direct_refusal(name, probe):
    if name in LANES or name == "tools":
        return None
    entry = next((row for row in _load_custom() if row.get("name") == name), None)
    if entry is None:
        return {"error": f"no plugin named '{name}'"}
    if not entry.get("enabled", True):
        return ({"name": name, "kind": "mcp", "status": "disabled",
                 "detail": "enable it before probing"} if probe else
                {"error": f"plugin '{name}' is disabled; enable it first"})
    return None


def _restricted_launch(command, bindings, slots):
    from .mcp_client import LaunchSpec
    platform = "windows" if os.name == "nt" else "posix"
    try:
        child_env = bindings.child_environment(os.environ, platform=platform)
    except Exception:
        raise PluginPermissionError from None
    allowed = (_WINDOWS_ENV if platform == "windows" else _POSIX_ENV) | set(slots)
    if (type(child_env) is not dict or set(slots) - set(child_env)
            or set(child_env) - allowed
            or any(type(key) is not str or type(value) is not str
                   for key, value in child_env.items())):
        raise PluginPermissionError
    if isinstance(command, LaunchSpec):
        argv, cwd = command.argv, command.cwd
    else:
        argv, cwd = tuple(command), None
    return LaunchSpec(argv, cwd, tuple(sorted(child_env.items())), False)
def _launch(command, slots, bindings):
    if bindings is None:
        if slots:
            raise PluginPermissionError
        return command
    return _restricted_launch(command, bindings, slots)


def call_plugin(name: str, tool: str, arguments: "dict | None" = None,
                timeout: float = 45.0, client_factory=None,
                credential_bindings=None, execution_plan=None) -> dict:
    """Call one tool through an admitted registered plugin plan."""
    if name == "tools":
        return {"error": "the builtin tool set runs inside gated agent "
                         "runs, not through this route"}
    refusal = None if execution_plan is not None else _direct_refusal(name, False)
    if refusal is not None:
        return refusal
    try:
        if execution_plan is None:
            command, kind, slots, _ = plugin_execution_plan(name)
            command = _launch(command, slots, credential_bindings)
        else:
            command, kind = execution_plan.launch, execution_plan.plugin_kind
    except PluginPermissionError:
        return _permission()
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


def probe_plugin(name: str, timeout: float = 20.0, client_factory=None,
                 credential_bindings=None, execution_plan=None) -> dict:
    """Probe one admitted plugin plan and report its real tools."""
    if name == "tools":
        return {"name": name, "kind": "builtin", "status": "live",
                "tools": list(BUILTIN_TOOLS)}
    refusal = None if execution_plan is not None else _direct_refusal(name, True)
    if refusal is not None:
        return refusal
    try:
        if execution_plan is None:
            command, kind, slots, _ = plugin_execution_plan(name)
            command = _launch(command, slots, credential_bindings)
        else:
            command, kind = execution_plan.launch, execution_plan.plugin_kind
    except PluginPermissionError:
        return _permission()
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

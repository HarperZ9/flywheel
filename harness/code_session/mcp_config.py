"""mcp_config.py -- MCP servers for a coding session, from config files.

Three files, all in the shape Claude Code and Cursor use, so a server written
for them works here unchanged:

  FLYWHEEL_HOME/mcp.json       yours; trusted
  <project>/.flywheel/mcp.json the project's; needs your yes
  <project>/.mcp.json          the project's; needs your yes

    {"mcpServers": {
       "files": {"command": "npx", "args": ["-y", "some-mcp-server"], "env": {}},
       "board": {"type": "http", "url": "https://example.org/mcp"}}}

A project file can name any program, so opening a folder must not start one
silently: project servers start only after a yes at the prompt, or with
`--trust-project-mcp`. With nobody to ask (`-p`), they are skipped and the
session says so. Each server's tools reach the model as
`mcp__<server>__<tool>`, go through the session's permission mode like any
command (ask, edit: ask; auto: run; plan: refused), and land on the ledger. A
server that fails to start is reported and skipped; it never stops the
session.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

USER_FILE = "mcp.json"
PROJECT_FILES = (Path(".flywheel") / "mcp.json", Path(".mcp.json"))
_SAFE = re.compile(r"[^A-Za-z0-9_]")


@dataclass
class ServerSpec:
    name: str
    source: str
    trusted: bool
    command: list = field(default_factory=list)
    env: dict = field(default_factory=dict)
    url: str = ""

    def record(self) -> dict:
        return {"name": self.name, "source": self.source, "trusted": self.trusted,
                "command": self.command[:1], "url": self.url}


def tool_prefix(server: str) -> str:
    return f"mcp__{_SAFE.sub('_', server)}__"


def _parse(path: Path, trusted: bool, errors: list) -> list[ServerSpec]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        errors.append(f"{path}: {e.__class__.__name__}")
        return []
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    if not isinstance(servers, dict):
        errors.append(f"{path}: expected an object with mcpServers")
        return []
    out = []
    for name, spec in servers.items():
        if not isinstance(spec, dict):
            errors.append(f"{path}: server {name!r} is not an object")
            continue
        url = str(spec.get("url", "")) if spec.get("type") in ("http", "streamable-http") \
            or ("url" in spec and "command" not in spec) else ""
        command = [str(spec["command"]), *map(str, spec.get("args", []))] \
            if spec.get("command") else []
        if not url and not command:
            errors.append(f"{path}: server {name!r} has neither command nor url")
            continue
        env = {str(k): str(v) for k, v in (spec.get("env") or {}).items()}
        out.append(ServerSpec(name=str(name), source=str(path), trusted=trusted,
                              command=command, env=env, url=url))
    return out


def load_specs(root: str, home: "str | None") -> "tuple[list[ServerSpec], list[str]]":
    """Every configured server, user first; a later file's name does not replace
    an earlier one (the first definition of a name wins)."""
    errors: list = []
    found: list[ServerSpec] = []
    paths = ([(Path(home) / USER_FILE, True)] if home else []) + \
        [(Path(root) / rel, False) for rel in PROJECT_FILES]
    from .plugins import plugin_roots
    paths += [(r / ".mcp.json", True) for r in plugin_roots(home)]   # installed: trusted
    for path, trusted in paths:
        if path.is_file():
            for spec in _parse(path, trusted, errors):
                if all(s.name != spec.name for s in found):
                    found.append(spec)
    return found, errors


def connect(spec: ServerSpec, *, timeout: float = 30.0, home: "str | None" = None):
    """Start one server and return (client, external tool entries). An HTTP
    server gets the bearer token from `flywheel mcp login` when one is stored."""
    from harness.mcp_client import LaunchSpec, MCPClient, MCPError, as_external_tools
    if spec.url:
        from harness.mcp_http import HttpTransport
        from .mcp_oauth import bearer_for
        token = bearer_for(home, spec.name) if home else None
        headers = {"authorization": f"Bearer {token}"} if token else {}
        client = MCPClient(transport=HttpTransport(spec.url, timeout=timeout, headers=headers))
        try:
            client.start()
        except MCPError as e:
            if "401" in str(e) and not token:
                raise MCPError(f"{spec.name} needs a sign-in: run `flywheel mcp login "
                               f"{spec.name}`") from None
            raise
    else:
        launch = LaunchSpec(argv=tuple(spec.command),
                            env_overrides=tuple(sorted(spec.env.items())))
        client = MCPClient(launch, timeout=timeout).start()
    return client, as_external_tools(client, prefix=tool_prefix(spec.name))


def attach(session, specs: list, *, ask=None, trust_project: bool = False,
           connector=None, home: "str | None" = None) -> list[dict]:
    """Start the servers the user allows and register their tools on the session.
    Returns one status row per server; every row also goes on the ledger."""
    rows = []
    for spec in specs:
        allowed = spec.trusted or trust_project or (ask is not None and ask(spec))
        if not allowed:
            rows.append({**spec.record(), "status": "skipped",
                         "reason": "project server not approved"})
            continue
        try:
            client, tools = (connector or (lambda sp: connect(sp, home=home)))(spec)
        except Exception as e:                   # a broken server never stops the session
            rows.append({**spec.record(), "status": "failed",
                         "reason": f"{e.__class__.__name__}: {e}"[:200]})
            continue
        session.executor.external.update(tools)
        session.mcp_clients.append(client)
        rows.append({**spec.record(), "status": "started", "tools": sorted(tools)})
    session.ledger.append("mcp", json.dumps(rows, sort_keys=True), {"servers": len(rows)})
    return rows

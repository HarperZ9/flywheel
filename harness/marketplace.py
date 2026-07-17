"""marketplace.py -- a discoverable catalog over the plugin registry.

Curated, offline-first: the built-in catalog lists real, public MCP stdio
servers by their launch argv, plus whatever the user adds to
~/.flywheel/catalog.json (same shape, merged by name). Installing an entry
registers it into the plugin registry -- nothing more. No downloads happen
here: the command runs only when probed or when a gated run allows MCP,
and entries that need credentials name the env var, never a value."""
from __future__ import annotations

import json
import os
from pathlib import Path

from .lanes import LANES
from .plugins import _load_custom, register_mcp

# Real, publicly documented MCP stdio servers. `requires` lists env var
# NAMES the server needs; presence is the user's business, values never
# appear anywhere in Flywheel.
CATALOG = [
    {"name": "filesystem",
     "command": ["npx", "-y", "@modelcontextprotocol/server-filesystem", "."],
     "detail": "reference filesystem server: read, write, and search a "
               "directory tree you name in the argv",
     "requires": []},
    {"name": "fetch",
     "command": ["npx", "-y", "@modelcontextprotocol/server-fetch"],
     "detail": "reference fetch server: retrieve and convert web content",
     "requires": []},
    {"name": "memory-graph",
     "command": ["npx", "-y", "@modelcontextprotocol/server-memory"],
     "detail": "reference knowledge-graph memory server",
     "requires": []},
    {"name": "github",
     "command": ["npx", "-y", "@modelcontextprotocol/server-github"],
     "detail": "GitHub repos, issues, and PRs over the API",
     "requires": ["GITHUB_PERSONAL_ACCESS_TOKEN"]},
    {"name": "playwright",
     "command": ["npx", "-y", "@playwright/mcp"],
     "detail": "drive a real browser: navigate, click, type, snapshot",
     "requires": []},
    {"name": "sqlite",
     "command": ["uvx", "mcp-server-sqlite", "--db-path", "data.db"],
     "detail": "query and inspect a SQLite database named in the argv",
     "requires": []},
    {"name": "git",
     "command": ["uvx", "mcp-server-git"],
     "detail": "reference git server: status, diff, log, and commit over "
               "local repositories",
     "requires": []},
    {"name": "time",
     "command": ["uvx", "mcp-server-time"],
     "detail": "reference time server: current time and timezone conversion",
     "requires": []},
    {"name": "sequential-thinking",
     "command": ["npx", "-y", "@modelcontextprotocol/server-sequential-thinking"],
     "detail": "reference structured-reasoning scratchpad server",
     "requires": []},
    {"name": "brave-search",
     "command": ["npx", "-y", "@modelcontextprotocol/server-brave-search"],
     "detail": "web search over the Brave Search API",
     "requires": ["BRAVE_API_KEY"]},
    {"name": "postgres",
     "command": ["npx", "-y", "@modelcontextprotocol/server-postgres",
                 "postgresql://localhost/postgres"],
     "detail": "read-only queries and schema inspection for the PostgreSQL "
               "database named in the argv",
     "requires": []},
    {"name": "gitlab",
     "command": ["npx", "-y", "@modelcontextprotocol/server-gitlab"],
     "detail": "GitLab projects, issues, and merge requests over the API",
     "requires": ["GITLAB_PERSONAL_ACCESS_TOKEN"]},
    {"name": "slack",
     "command": ["npx", "-y", "@modelcontextprotocol/server-slack"],
     "detail": "read and post in Slack channels over a bot token",
     "requires": ["SLACK_BOT_TOKEN", "SLACK_TEAM_ID"]},
    {"name": "puppeteer",
     "command": ["npx", "-y", "@modelcontextprotocol/server-puppeteer"],
     "detail": "headless-Chrome automation: navigate, screenshot, evaluate",
     "requires": []},
    {"name": "chrome-devtools",
     "command": ["npx", "-y", "chrome-devtools-mcp"],
     "detail": "Chrome DevTools protocol: performance traces, network, "
               "console, and DOM inspection of a live browser",
     "requires": []},
    {"name": "context7",
     "command": ["npx", "-y", "@upstash/context7-mcp"],
     "detail": "up-to-date library documentation and code examples by "
               "package name",
     "requires": []},
    {"name": "everything",
     "command": ["npx", "-y", "@modelcontextprotocol/server-everything"],
     "detail": "the MCP conformance test server: every protocol feature, "
               "for exercising a client end to end",
     "requires": []},
]


def _user_catalog_path() -> Path:
    home = os.environ.get("FLYWHEEL_HOME") or os.path.join(
        os.path.expanduser("~"), ".flywheel")
    return Path(home) / "catalog.json"


def _merged_catalog() -> list:
    entries = {e["name"]: {**e, "origin": "builtin"} for e in CATALOG}
    p = _user_catalog_path()
    if p.exists():
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
            for e in doc.get("entries", []):
                if isinstance(e, dict) and e.get("name") and \
                        isinstance(e.get("command"), list):
                    e.setdefault("requires", [])
                    e.setdefault("detail", "user-catalog entry")
                    entries[e["name"]] = {**e, "origin": "user"}
        except (OSError, ValueError):
            pass  # a broken user catalog never hides the builtin one
    return list(entries.values())


def marketplace_catalog() -> dict:
    """The catalog with an `installed` flag cross-checked against the plugin
    registry and the bundled lanes."""
    registered = {e.get("name") for e in _load_custom()}
    out = []
    for e in _merged_catalog():
        out.append({**e,
                    "installed": e["name"] in registered or e["name"] in LANES,
                    "credential_note": ("needs " + ", ".join(e["requires"])
                                        + " in the environment"
                                        if e["requires"] else "")})
    return {"schema": "flywheel.marketplace/v1",
            "entries": sorted(out, key=lambda e: e["name"]),
            "n": len(out),
            "note": "installing registers the launch command into the plugin "
                    "registry; nothing downloads or runs until probed or "
                    "granted in a gated run"}


def install_from_catalog(name: str) -> dict:
    entry = next((e for e in _merged_catalog() if e["name"] == name), None)
    if entry is None:
        return {"error": f"no catalog entry named '{name}'"}
    return register_mcp(entry["name"], entry["command"],
                        detail=entry.get("detail", ""))


def add_user_entry(name: str, command: list, detail: str = "",
                   requires: "list | None" = None) -> dict:
    """Add (or replace) an entry in the user catalog. It becomes discoverable
    in the merged catalog; nothing runs until installed AND probed or granted
    in a gated run. Builtin names cannot be shadowed, and `requires` carries
    env var NAMES only — a value-shaped entry is refused outright."""
    name = (name or "").strip()
    if not name:
        return {"error": "provide a non-empty 'name'"}
    if any(e["name"] == name for e in CATALOG):
        return {"error": f"'{name}' is a builtin catalog entry; "
                         "pick another name"}
    if not isinstance(command, list) or not command or \
            not all(isinstance(c, str) and c.strip() for c in command):
        return {"error": "provide 'command' as a non-empty list of strings"}
    reqs = []
    for r in (requires or []):
        r = str(r).strip()
        if not r:
            continue
        if "=" in r or not r.replace("_", "").isalnum():
            return {"error": f"'{r}' is not an env var NAME; requires lists "
                             "names only, never values"}
        reqs.append(r)
    p = _user_catalog_path()
    doc = {"entries": []}
    if p.exists():
        try:
            loaded = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(loaded.get("entries"), list):
                doc = loaded
        except (OSError, ValueError):
            pass  # rebuilding a broken user catalog is the right recovery
    entries = [e for e in doc.get("entries", [])
               if isinstance(e, dict) and e.get("name") != name]
    entry = {"name": name, "command": [c.strip() for c in command],
             "detail": detail.strip() or "user-catalog entry",
             "requires": reqs}
    entries.append(entry)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"entries": entries}, indent=2), encoding="utf-8")
    return {"schema": "flywheel.marketplace-entry/v1", "added": True, **entry,
            "note": "saved to the user catalog; install registers it into "
                    "the plugin registry when you choose"}


def remove_user_entry(name: str) -> dict:
    """Remove a user catalog entry by name. Builtin entries are not files
    and cannot be removed, only left uninstalled."""
    name = (name or "").strip()
    p = _user_catalog_path()
    if not p.exists():
        return {"error": f"no user catalog entry named '{name}'"}
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"error": "the user catalog file is unreadable; fix or "
                         "delete ~/.flywheel/catalog.json"}
    entries = [e for e in doc.get("entries", []) if isinstance(e, dict)]
    keep = [e for e in entries if e.get("name") != name]
    if len(keep) == len(entries):
        return {"error": f"no user catalog entry named '{name}'"}
    p.write_text(json.dumps({"entries": keep}, indent=2), encoding="utf-8")
    return {"removed": True, "name": name}

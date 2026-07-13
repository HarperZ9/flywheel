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
]


def _user_catalog_path() -> Path:
    home = os.environ.get("FLYWHEEL_HOME") or os.path.join(
        os.path.expanduser("~"), ".flywheel")
    return Path(home) / "catalog.json"


def _merged_catalog() -> list:
    entries = {e["name"]: dict(e) for e in CATALOG}
    p = _user_catalog_path()
    if p.exists():
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
            for e in doc.get("entries", []):
                if isinstance(e, dict) and e.get("name") and \
                        isinstance(e.get("command"), list):
                    e.setdefault("requires", [])
                    e.setdefault("detail", "user-catalog entry")
                    entries[e["name"]] = e
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

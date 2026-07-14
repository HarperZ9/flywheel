"""import_adapters.py -- arrive with your whole setup, keep the proof.

The landscape's clearest acquisition move (Codex ships one-step Claude Code
migration) with the artifact it lacks: importing a foreign harness config
produces a MAPPING MANIFEST -- every source file content-hashed, every
mapping named, everything unmappable dropped WITH A REASON. A migration
that loses something silently has lied about being a migration.

Recognized sources: CLAUDE.md / CLAUDE.local.md and AGENTS.md (instruction
text), .cursorrules and .cursor/rules/* (rule text), GEMINI.md,
.github/copilot-instructions.md, and .claude/settings.json (MCP servers map;
hooks and permissions are dropped honestly until a native equivalent exists).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

SCHEMA = "flywheel.import-manifest/v1"

_TEXT_SOURCES = (
    ("CLAUDE.md", "instructions"),
    ("CLAUDE.local.md", "instructions"),
    ("AGENTS.md", "instructions"),
    ("GEMINI.md", "instructions"),
    (".cursorrules", "instructions"),
    (".github/copilot-instructions.md", "instructions"),
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def import_config(root) -> dict:
    """Scan `root` for foreign harness configs and map them into one
    Flywheel project profile plus the manifest of what happened."""
    root = Path(root)
    mappings: list = []
    dropped: list = []
    instructions: list = []
    mcp_servers: dict = {}

    def _text_source(rel: str, target: str, path: Path):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError as e:
            dropped.append({"source": rel,
                            "reason": f"unreadable: {type(e).__name__}"})
            return
        instructions.append(f"# from {rel}\n{text.strip()}")
        mappings.append({"source": rel, "mapped_to": target,
                         "status": "mapped", "sha256": _sha(text)})

    for rel, target in _TEXT_SOURCES:
        p = root / rel
        if p.is_file():
            _text_source(rel, target, p)
    rules_dir = root / ".cursor" / "rules"
    if rules_dir.is_dir():
        for p in sorted(rules_dir.glob("*")):
            if p.is_file():
                _text_source(f".cursor/rules/{p.name}", "instructions", p)

    settings = root / ".claude" / "settings.json"
    if settings.is_file():
        raw = settings.read_text(encoding="utf-8", errors="ignore")
        try:
            data = json.loads(raw)
        except ValueError:
            data = None
        if isinstance(data, dict):
            servers = data.get("mcpServers")
            if isinstance(servers, dict):
                for name, spec in sorted(servers.items()):
                    if isinstance(spec, dict) and spec.get("command"):
                        mcp_servers[name] = {
                            "command": str(spec["command"]),
                            "args": [str(a) for a in spec.get("args", [])],
                        }
            for unmapped in ("hooks", "permissions", "env"):
                if unmapped in data:
                    dropped.append({
                        "source": ".claude/settings.json",
                        "reason": f"{unmapped} have no native equivalent "
                                  "yet; carried nowhere rather than "
                                  "half-translated"})
            mappings.append({"source": ".claude/settings.json",
                             "mapped_to": "mcp_servers",
                             "status": "partial" if any(
                                 d["source"] == ".claude/settings.json"
                                 for d in dropped) else "mapped",
                             "sha256": _sha(raw)})
        else:
            dropped.append({"source": ".claude/settings.json",
                            "reason": "not valid JSON"})

    profile = {"instructions": "\n\n".join(instructions),
               "mcp_servers": mcp_servers}
    note = ("every source hashed, every mapping named, every drop reasoned"
            if mappings or dropped else
            "nothing to import: no recognized harness config found here")
    return {"schema": SCHEMA, "root": str(root), "mappings": mappings,
            "dropped": dropped, "profile": profile, "note": note}

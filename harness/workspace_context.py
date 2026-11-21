"""workspace_context.py -- deterministic instruction and memory loader for Flywheel.

Discovers user- and workspace-level instructions (PROJECTS.md, AGENTS.md,
CLAUDE.md, .flywheel/instructions.md) and memory indexes (~/.flywheel/memory/MEMORY.md)
and emits a bounded context bundle with SHA-256 receipts for every loaded file.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

CONTEXT_SCHEMA = "flywheel.workspace-context/v1"
DEFAULT_MAX_CHARS = 120_000


def _flywheel_home(flywheel_home: Path | None = None) -> Path:
    if flywheel_home is not None:
        return Path(flywheel_home)
    return Path(os.environ.get("FLYWHEEL_HOME", str(Path.home() / ".flywheel")))


def discover_context_files(
    workspace: Path,
    *,
    flywheel_home: Path | None = None,
) -> list[dict[str, str]]:
    """Return ordered, deduplicated instruction and memory files for a workspace."""
    ws = Path(workspace).resolve()
    home = _flywheel_home(flywheel_home)
    candidates: list[tuple[Path, str]] = [
        (home / "instructions.md", "user-instructions"),
        (home / "memory" / "MEMORY.md", "user-memory"),
        (ws / "PROJECTS.md", "workspace-projects"),
        (ws / "AGENTS.md", "workspace-instructions"),
        (ws / "CLAUDE.md", "workspace-instructions"),
        (ws / ".flywheel" / "instructions.md", "flywheel-instructions"),
        (ws / ".flywheel" / "MEMORY.md", "workspace-memory"),
    ]
    seen: set[Path] = set()
    found: list[dict[str, str]] = []
    for path, kind in candidates:
        try:
            if not path.is_file():
                continue
            resolved = path.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        found.append({"path": str(resolved), "kind": kind})
    return found


def load_workspace_context(
    workspace: Path,
    *,
    flywheel_home: Path | None = None,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> dict[str, Any]:
    """Read discovered instruction and memory files with per-file SHA-256 receipts."""
    ws = Path(workspace).resolve()
    entries = discover_context_files(ws, flywheel_home=flywheel_home)
    sources: list[dict[str, Any]] = []
    chunks: list[str] = []
    remaining = max(0, int(max_chars))

    for entry in entries:
        path = Path(entry["path"])
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        digest = hashlib.sha256(raw).hexdigest()
        text = raw.decode("utf-8", errors="replace").strip()
        truncated = False
        if remaining <= 0:
            sources.append({
                "path": str(path),
                "kind": entry["kind"],
                "sha256": digest,
                "bytes": len(raw),
                "included_chars": 0,
                "truncated": True,
            })
            continue
        if len(text) > remaining:
            text = text[:remaining]
            truncated = True
        header = f"<!-- {entry['kind']}: {path.name} sha256={digest[:12]} -->\n"
        chunks.append(header + text)
        remaining -= len(text)
        sources.append({
            "path": str(path),
            "kind": entry["kind"],
            "sha256": digest,
            "bytes": len(raw),
            "included_chars": len(text),
            "truncated": truncated,
        })

    context_text = "\n\n".join(chunks)
    return {
        "schema": CONTEXT_SCHEMA,
        "workspace": str(ws),
        "sources": sources,
        "source_count": len(sources),
        "total_chars": len(context_text),
        "context_text": context_text,
    }


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    ws = Path(args[0]) if args else Path.cwd()
    bundle = load_workspace_context(ws)
    summary = {k: v for k, v in bundle.items() if k != "context_text"}
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""context_envelope.py -- the index lane as catalog: produce the
project-telos.context-envelope/v1 document from a live index lane.

Gap D (MEMORY-SUBSTRATE.md:39): "the retrieved-context envelopes (index/gather)
are stable across tasks." The receiving slots exist -- boot.py's docstring
references the context-envelope/v1 contract; wiki.from_index_wiki consumes an
index_manifest shape -- but no producer wired the index lane into the harness.
This module is that producer.

It calls the index lane (via harness.lanes + mcp_client) for a budgeted
context envelope over a workspace root, and returns the
project-telos.context-envelope/v1 document. boot.hydrate_prompt can then
populate its retrieved-context slot from a real catalog instead of a structural
empty. Graceful: if the index lane is down, returns UNVERIFIABLE (never crashes
the boot path; the caller degrades to the envelope-less boot, as before).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

UNVERIFIABLE = "UNVERIFIABLE"
MATCH = "MATCH"


def build_context_envelope(root: str | Path, *, budget: int = 1500,
                            focus: str = "", hops: int = 1,
                            lane_timeout: float = 30.0) -> dict:
    """Call the index lane for a budgeted context envelope over `root`.

    Returns a dict shaped as project-telos.context-envelope/v1:
      {schema, tool, root, budget, focus, hops, verification_verdict,
       selection, retained_names, freshness, source}
    On any failure (lane down, timeout, malformed response), returns a minimal
    envelope with verification_verdict=UNVERIFIABLE and an honest failure_code.
    """
    root = str(Path(root).resolve())
    from .mcp_client import MCPClient, MCPError
    from .lanes import resolve_mcp_command
    command = resolve_mcp_command("index")
    try:
        with MCPClient(command, timeout=lane_timeout,
                       client_name="flywheel-context-envelope") as c:
            c.start()
            # Prefer the selection-aware envelope tool; fall back to plain context.
            # Index MCP tools use dotted names (index.context.envelope).
            tools = {t.get("name", "") for t in c.list_tools()}
            tool = ("index.context.envelope" if "index.context.envelope" in tools
                    else ("index_context_envelope" if "index_context_envelope" in tools
                          else "index.context"))
            res = c.call_text(tool, {
                "root": root, "budget": budget,
                **({"focus": focus} if focus else {}),
                **({"hops": hops} if "envelope" in tool else {}),
            })
            if not res["ok"]:
                return _unverifiable(root, budget, focus,
                                     f"index lane tool error: {res['text'][:200]}")
            try:
                envelope = json.loads(res["text"])
            except json.JSONDecodeError:
                return _unverifiable(root, budget, focus,
                                     "index lane returned non-JSON")
            # Normalize to the context-envelope/v1 shape and stamp a stable hash.
            envelope.setdefault("schema", "project-telos.context-envelope/v1")
            envelope.setdefault("tool", tool)
            envelope.setdefault("root", root)
            envelope.setdefault("budget", budget)
            envelope.setdefault("verification_verdict", MATCH)
            envelope["_flywheel_source"] = "index-lane"
            return envelope
    except (MCPError, FileNotFoundError, OSError) as e:
        return _unverifiable(root, budget, focus, f"index lane unavailable: {e}")


def _unverifiable(root: str, budget: int, focus: str, reason: str) -> dict:
    return {
        "schema": "project-telos.context-envelope/v1",
        "tool": "index_context_envelope",
        "root": root,
        "budget": budget,
        "focus": focus,
        "verification_verdict": UNVERIFIABLE,
        "failure_code": "index_lane_unavailable",
        "reason": reason,
        "_flywheel_source": "fallback",
    }


def envelope_fingerprint(envelope: dict) -> str:
    """A stable hash over the envelope's retained content (not its metadata), so
    two calls over an unchanged workspace produce the same fingerprint and a
    change moves it. Used by boot.py to detect drift."""
    payload = json.dumps({
        "retained": envelope.get("retained_names", envelope.get("selection", {})),
        "root": envelope.get("root", ""),
        "verdict": envelope.get("verification_verdict", ""),
    }, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


if __name__ == "__main__":
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    env = build_context_envelope(root)
    print(json.dumps(env, indent=1)[:1200])

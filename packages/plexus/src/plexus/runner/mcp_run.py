"""mcp_run.py: the MCP server with plexus_fanout added (`plexus mcp --run`).

The plain server (`plexus mcp`) only reads manifests. This one also starts
the tools fanout routes to, inside the policy and budgets in sense_data, so it
is a separate command a harness opts into.
"""
from __future__ import annotations

import json

from .. import mcp as _base

FANOUT_TOOL = {
    "name": "plexus_fanout",
    "title": "Run an item through every tool that accepts it",
    "description": ("Detect the item's input kinds, run every sense tool whose kinds match (one at a time, "
                    "each under its time and memory budget, inside the policy in sense_data/policy.json), "
                    "and write one bundle: each tool's output, time, peak memory, status and error, plus a "
                    "receipt. Failed, refused and unreachable tools are rows in the bundle, never dropped. "
                    "Network use is off unless granted per tool. dry_run plans without running."),
    "inputSchema": {"type": "object", "required": ["item"], "properties": {
        "item": {"type": "string", "description": "a file path, folder, URL or short literal"},
        "out": {"type": "string", "description": "folder for the bundle (default plexus-fanout)"},
        "kinds": {"type": "array", "items": {"type": "string"},
                  "description": "kinds the bytes cannot show (geometry, claim)"},
        "grant_network": {"type": "array", "items": {"type": "string"},
                          "description": "tool ids allowed to use the network for this call"},
        "only": {"type": "array", "items": {"type": "string"}, "description": "run only these tool ids"},
        "config": {"type": "string", "description": "local config with roots and MCP servers"},
        "dry_run": {"type": "boolean"}}},
    "annotations": {"title": "Run an item through every tool that accepts it", "readOnlyHint": False,
                    "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
}


def _fanout(args: dict) -> dict:
    from .fanout import fanout, load_config
    from ..cli_senses import _summary
    res = fanout(args.get("item", ""), args.get("out") or "plexus-fanout",
                 extra_kinds=args.get("kinds") or [], cfg=load_config(args.get("config")),
                 grants={"network": args.get("grant_network") or [], "kinds": []},
                 dry_run=bool(args.get("dry_run")), only=set(args.get("only") or []) or None)
    return _summary(res)


def handle_run(req: dict):
    if isinstance(req, dict) and req.get("method") == "tools/list" and "id" in req:
        resp = _base.handle(req)
        resp["result"]["tools"] = list(resp["result"]["tools"]) + [FANOUT_TOOL]
        return resp
    params = req.get("params") if isinstance(req, dict) else None
    if (isinstance(req, dict) and req.get("method") == "tools/call" and isinstance(params, dict)
            and params.get("name") == "plexus_fanout" and req.get("jsonrpc") == "2.0" and "id" in req):
        try:
            out = {"content": [{"type": "text", "text": json.dumps(_fanout(params.get("arguments") or {}),
                                                                    indent=2, ensure_ascii=False)}]}
        except Exception as e:                       # a tool error is a result, not a crash
            out = {"content": [{"type": "text", "text": f"[error] {type(e).__name__}: {e}"}], "isError": True}
        return {"jsonrpc": "2.0", "id": req["id"], "result": out}
    return _base.handle(req)

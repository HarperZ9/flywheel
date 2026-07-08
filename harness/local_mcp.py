"""local_mcp.py — expose the local/multi-endpoint agent as an MCP server.

So any harness (Claude Code included) can call this agent as a tool: check which
tiers are live, get a one-shot completion, or run a gated agentic task with a
witnessed ledger. Zero-dep stdio JSON-RPC 2.0, the shape every flagship speaks.
`handle()` is transport-free and testable; `serve()` is the thin stdio loop.
"""
from __future__ import annotations

import json
import sys

from .local_agent import LocalAgent, available_backends, health_report
from .local_loop import run_agent
from .local_session import SessionLedger
from .local_tools import ToolExecutor, ToolGate

PROTOCOL = "2025-06-18"
__version__ = "0.1.0"

_ONLINE = {"online": {"type": "boolean", "description": "include codex/claude/gemini/deepseek"}}

TOOLS = [
    {"name": "local_agent_health",
     "description": "Report which model tiers are live (local serve/ollama, plus online providers when online=true).",
     "inputSchema": {"type": "object", "properties": dict(_ONLINE)}},
    {"name": "local_agent_chat",
     "description": "One-shot completion from the first healthy tier, with a per-turn receipt.",
     "inputSchema": {"type": "object", "required": ["prompt"],
                     "properties": {"prompt": {"type": "string"},
                                    "backend": {"type": "string"}, **_ONLINE}}},
    {"name": "local_agent_run",
     "description": "Run a gated agentic task (tools sandboxed to root; write/exec off unless allowed); returns the final answer and a verifiable ledger checkpoint.",
     "inputSchema": {"type": "object", "required": ["goal"],
                     "properties": {"goal": {"type": "string"}, "root": {"type": "string"},
                                    "allow_write": {"type": "boolean"}, "allow_exec": {"type": "boolean"},
                                    "max_steps": {"type": "integer"}, **_ONLINE}}},
]


def _backends(args: dict) -> list:
    bs = available_backends()
    if args.get("online"):
        from .endpoints import build_endpoints
        bs = bs + build_endpoints()
    return bs


def _agent(args: dict) -> LocalAgent:
    return LocalAgent(backends=_backends(args), prefer=args.get("backend", "auto"),
                      max_tokens=int(args.get("max_tokens", 512)))


def _text(obj) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(obj, indent=2)}]}


def _call(params: dict) -> dict:
    name, args = params.get("name"), params.get("arguments", {}) or {}
    try:
        if name == "local_agent_health":
            return _text(health_report(_backends(args)))
        if name == "local_agent_chat":
            resp = _agent(args).send(args["prompt"])
            return _text({"text": resp["content"][0]["text"], "backend": resp.get("backend"),
                          "receipt": resp.get("x_receipt", {}).get("receipt_id")})
        if name == "local_agent_run":
            ex = ToolExecutor(root=args.get("root", "."),
                              gate=ToolGate(allow_write=bool(args.get("allow_write")),
                                            allow_exec=bool(args.get("allow_exec"))))
            r = run_agent(_agent(args), args["goal"], ex, SessionLedger(),
                          max_steps=int(args.get("max_steps", 6)))
            return _text({"final": r["final"], "steps": r["steps"],
                          "verified": r["verified"], "checkpoint": r["checkpoint"]})
        return {"content": [{"type": "text", "text": f"unknown tool {name!r}"}], "isError": True}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"[error] {type(e).__name__}: {e}"}],
                "isError": True}


def _ok(rid, result):
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def handle(req: dict):
    method, rid = req.get("method"), req.get("id")
    if method == "initialize":
        return _ok(rid, {"protocolVersion": PROTOCOL, "capabilities": {"tools": {}},
                         "serverInfo": {"name": "local-agent", "version": __version__}})
    if method == "tools/list":
        return _ok(rid, {"tools": TOOLS})
    if method == "tools/call":
        return _ok(rid, _call(req.get("params", {})))
    if rid is None:
        return None
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"method not found: {method}"}}


def serve(stdin=None, stdout=None) -> int:
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle(req)
        if resp is not None:
            stdout.write(json.dumps(resp) + "\n")
            stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(serve())

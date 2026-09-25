"""local_mcp.py — expose the local/multi-endpoint agent as an MCP server.

So any harness (Claude Code included) can call this agent as a tool: check which
tiers are live, get a one-shot completion, or run a gated agentic task with a
witnessed ledger. Zero-dep stdio JSON-RPC 2.0, the shape every flagship speaks.
`handle()` is transport-free and testable; `serve()` is the thin stdio loop.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .local_agent import LocalAgent, available_backends, health_report
from .local_agent_grants import (
    AgentRunGrants, GrantRefusal, check_online, grants_from_config, refused_grants,
    resolve_run,
)
from .local_loop import run_agent
from .local_session import SessionLedger
from .local_tools import ToolExecutor, ToolGate
from .receipt_operations import (
    ReceiptOperationError,
    mcp_tool_descriptors as receipt_mcp_tool_descriptors,
    verify_receipt_inclusion,
)
from .run_paths import run_root_default
from .tool_sandbox_bridge import fallback_from_env, make_sandboxed_runner
from .skill_resources import list_resources, read_resource
from .context_memory_bridge import (
    ContextMemoryBridge, ContextMemoryError, context_memory_tool_descriptors,
)

PROTOCOL = "2025-06-18"
__version__ = "0.1.0"

_ONLINE = {"online": {"type": "boolean", "description": "include codex/claude/gemini/deepseek; for chat and run, true is refused unless the operator granted online tiers"}}

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
     "description": "Run a gated agentic task confined to the operator's workspace. Write and exec are granted by the operator when the server starts; the arguments can only narrow them. Returns the final answer and a verifiable ledger checkpoint.",
     "inputSchema": {"type": "object", "required": ["goal"],
                     "properties": {"goal": {"type": "string"},
                                    "root": {"type": "string", "description": "directory inside the operator's workspace; relative paths are taken from the workspace"},
                                    "allow_write": {"type": "boolean", "description": "false narrows the operator grant; true is refused unless the operator granted write"},
                                    "allow_exec": {"type": "boolean", "description": "false narrows the operator grant; true is refused unless the operator granted exec"},
                                    "max_steps": {"type": "integer"}, **_ONLINE}}},
    {"name": "local-model.status",
     "description": "Liveness and identity of the local-model lane (name, version, protocol). Network-free, for a fast health probe.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "local-model.doctor",
     "description": "Readiness diagnostic: identity plus the tiers this lane would try and the tools it exposes. Network-free, so it reports no reachability; local_agent_health is the tool that pings a tier.",
     "inputSchema": {"type": "object", "properties": {}}},
] + context_memory_tool_descriptors() + receipt_mcp_tool_descriptors()


def _backends(args: dict) -> list:
    bs = available_backends()
    if args.get("online"):
        from .endpoints import build_endpoints
        bs = bs + build_endpoints()
    return bs


def _agent(args: dict) -> LocalAgent:
    return LocalAgent(backends=_backends(args), prefer=args.get("backend", "auto"),
                      max_tokens=int(args.get("max_tokens", 512)))


def _local_tiers() -> frozenset:
    return frozenset(("auto", *(getattr(b, "name", "") for b in available_backends())))


def _checked_online(args: dict, grants) -> None:
    """Refuse an online or plan-mode tier the operator did not grant."""
    check_online(args, grants or grants_from_config(), _local_tiers())


def _pin_cli_cwd(agent, root: str) -> None:
    """A plan-mode CLI tier runs in the run's resolved root, not the server's cwd."""
    from .endpoints import CliBackend
    for backend in getattr(agent, "backends", ()):
        if isinstance(backend, CliBackend):
            backend.cwd = root


def _lane_health(deep: bool) -> dict:
    """Identity for the lane probe, and for doctor the tiers and tools behind it.

    `ok` here is liveness, not health: it says this server answered, which is
    the only thing a network-free call can establish. `available_backends()`
    constructs its two tiers unconditionally, so listing them says what the
    lane would try and nothing about what is reachable. The reachability field
    says `unprobed` rather than carrying a verdict nothing measured.
    """
    info = {"ok": True, "server": "local-model", "version": __version__,
            "protocol": PROTOCOL}
    if deep:
        info["tiers_configured"] = [type(b).__name__ for b in available_backends()]
        info["reachability"] = "unprobed; call local_agent_health to ping"
        info["tools"] = [t["name"] for t in TOOLS]
    return info


def _text(obj) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(obj, indent=2)}]}


def _structured(obj: dict) -> dict:
    result = _text(obj)
    result["structuredContent"] = obj
    return result


def _error(code: str, message: str) -> dict:
    result = _structured({"error": {"code": code, "message": message}})
    result["isError"] = True
    return result


def _receipt_ledger(root=None, run_root=None) -> dict:
    from . import gateway as _gateway
    repo_root = Path(root) if root is not None else _gateway.REPO
    receipts_root = Path(run_root) if run_root is not None else run_root_default()
    return _gateway.receipts_ledger(repo_root, receipts_root)


def _receipt_reader(root, run_root):
    if root is None and run_root is None:
        return _receipt_ledger
    return lambda: _receipt_ledger(root, run_root)


def _context_memory_bridge() -> ContextMemoryBridge:
    return ContextMemoryBridge()


def _call(params: dict, *, root=None, run_root=None, grants=None) -> dict:
    name, args = params.get("name"), params.get("arguments", {}) or {}
    try:
        if name == "local_agent_health":
            return _text(health_report(_backends(args)))
        if name == "local_agent_chat":
            _checked_online(args, grants)
            resp = _agent(args).send(args["prompt"])
            return _text({"text": resp["content"][0]["text"], "backend": resp.get("backend"),
                          "receipt": resp.get("x_receipt", {}).get("receipt_id")})
        if name == "local_agent_run":
            grants = grants or grants_from_config()
            run_root_dir, allow_write, allow_exec = resolve_run(args, grants)
            _checked_online(args, grants)
            ex = ToolExecutor(root=run_root_dir,
                              gate=ToolGate(allow_write=allow_write, allow_exec=allow_exec),
                              runner=make_sandboxed_runner(
                                  bindings=None,
                                  on_unavailable=fallback_from_env()))
            from harness import tool_receipts
            agent = _agent(args)
            _pin_cli_cwd(agent, run_root_dir)
            r = run_agent(agent, args["goal"], ex, SessionLedger(),
                          max_steps=int(args.get("max_steps", 6)),
                          sign_key=tool_receipts.new_session_key())
            return _text({"final": r["final"], "steps": r["steps"],
                          "verified": r["verified"], "checkpoint": r["checkpoint"]})
        if name in ("local-model.status", "local-model.doctor"):
            return _text(_lane_health(name == "local-model.doctor"))
        if name == "flywheel.context.health":
            return _text(_context_memory_bridge().health(owner_ref=args.get("owner_ref")))
        if name == "flywheel.context.capture":
            owner_ref = args.get("owner_ref")
            request = {k: v for k, v in args.items() if k != "owner_ref"}
            return _text(_context_memory_bridge().capture(owner_ref, request))
        if name == "flywheel.context.preflight":
            owner_ref = args.get("owner_ref")
            request = {k: v for k, v in args.items() if k != "owner_ref"}
            return _text(_context_memory_bridge().preflight(owner_ref, request))
        if name == "receipt.verify_inclusion":
            return _structured(verify_receipt_inclusion(
                args, ledger=_receipt_reader(root, run_root)))
        return {"content": [{"type": "text", "text": f"unknown tool {name!r}"}], "isError": True}
    except (ReceiptOperationError, GrantRefusal) as e:
        return _error(e.code, e.message)
    except ContextMemoryError as e:
        return _error(e.code, e.message)
    except Exception as e:
        if name == "receipt.verify_inclusion":
            return _error("RECEIPTS_LEDGER_UNAVAILABLE",
                          "the receipts ledger could not be read")
        return {"content": [{"type": "text", "text": f"[error] {type(e).__name__}: {e}"}],
                "isError": True}


def _ok(rid, result):
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def handle(req: dict, *, root=None, run_root=None, grants: AgentRunGrants | None = None):
    method, rid = req.get("method"), req.get("id")
    if method == "initialize":
        return _ok(rid, {"protocolVersion": PROTOCOL,
                         "capabilities": {"tools": {}, "resources": {}},
                         "serverInfo": {"name": "local-agent", "version": __version__}})
    if method == "tools/list":
        return _ok(rid, {"tools": TOOLS})
    if method == "tools/call":
        return _ok(rid, _call(req.get("params", {}),
                              root=root, run_root=run_root, grants=grants))
    if method == "resources/list":
        return _ok(rid, list_resources())
    if method == "resources/read":
        params = req.get("params")
        if not isinstance(params, dict):
            return {"jsonrpc": "2.0", "id": rid,
                    "error": {"code": -32602, "message": "resource params must be an object"}}
        try:
            return _ok(rid, read_resource(params.get("uri")))
        except KeyError as exc:
            return {"jsonrpc": "2.0", "id": rid,
                    "error": {"code": -32602, "message": str(exc)}}
    if rid is None:
        return None
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"method not found: {method}"}}


def serve(stdin=None, stdout=None, *, root=None, run_root=None,
          grants: AgentRunGrants | None = None) -> int:
    """Serve stdio JSON-RPC. local_agent_run grants are frozen once, here, from
    the start configuration; nothing a request carries can change them."""
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    if grants is None:
        try:
            grants = grants_from_config()
        except GrantRefusal as refusal:
            # Keep serving health, chat and receipts; every run gets the refusal.
            print(f"[local-agent] {refusal.code}: {refusal.message}; "
                  "local_agent_run is refused", file=sys.stderr, flush=True)
            grants = refused_grants(refusal)
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle(req, root=root, run_root=run_root, grants=grants)
        if resp is not None:
            stdout.write(json.dumps(resp) + "\n")
            stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(serve())

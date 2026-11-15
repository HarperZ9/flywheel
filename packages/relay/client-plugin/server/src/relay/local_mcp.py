"""local_mcp.py — expose the local/multi-endpoint agent as an MCP server.

So any harness (Claude Code included) can call this agent as a tool: check which
tiers are live, get a one-shot completion, or run a gated agentic task with a
witnessed ledger. Zero-dep stdio JSON-RPC 2.0, the shape every flagship speaks.
`handle()` is transport-free and testable; `serve()` is the thin stdio loop.
Write and exec are granted by whoever starts the server (see mcp_grants); a tool
argument can only narrow them.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from .async_runs import RunRegistry
from .local_agent import LocalAgent, available_backends, health_report
from .local_loop import run_agent
from .local_session import SessionLedger
from .local_tools import ToolExecutor, ToolGate
from .mcp_paths import GuardedExecutor, ProtectedPaths
from .mcp_grants import (
    SURFACE_EXEC_REFUSED,
    StartGrants,
    grants_from_launch,
    launch_root,
    pin_root,
)
from .mcp_request import (
    MCPInputError,
    as_bool as _as_bool,
    as_int as _as_int,
    as_str as _as_str,
    cli_tier_profiles,
    refuse_cli_tier,
    request_binding,
    run_projection,
)
from .mcp_schema import TOOLS

PROTOCOL = "2025-06-18"
__version__ = "0.7.0"

# Background runs, so a phone can start a long agentic task and poll it instead of
# holding one blocking HTTP request open across a flaky mobile network. With
# RELAY_RUN_ROOT set, runs persist so a run_id survives a server restart.
RUNS = RunRegistry(run_root=os.environ.get("RELAY_RUN_ROOT") or None)

# The most any run may do, fixed at launch by serve() or a launcher. Off until then.
_GRANTS = StartGrants()
_CLI_TIERS = True  # False: no claude/codex CLI is built, probed or started (see serve)


def configure(grants: StartGrants) -> None:
    """Set the launch grants and pin the launch root. Runs already started keep
    the gate and root they began with."""
    global _GRANTS
    _GRANTS = pin_root(grants)


def _request_binding(args: dict) -> dict:
    return request_binding(args, _GRANTS)


def _call_exec_ok() -> bool:
    """Exec for a call with no run gate (chat, health): the launch grant, unless
    the surface refuses exec for this request."""
    return _GRANTS.allow_exec and not SURFACE_EXEC_REFUSED.get()


def _backends(args: dict, exec_ok: bool) -> list:
    bs = available_backends(model=_as_str(args, "model", ""))
    if _as_bool(args, "online"):
        from .endpoints import CliBackend, build_endpoints
        online = build_endpoints(modes=("plan", "api", "provider", "cloud") if _CLI_TIERS
                                 else ("api", "provider", "cloud"))
        if not exec_ok:
            # codex exec / claude -p run an agent with its own shell.
            online = [b for b in online if not isinstance(b, CliBackend)]
        bs = bs + online
    return bs


def _agent(args: dict, request_binding: dict | None = None) -> LocalAgent:
    if request_binding is None:
        exec_ok = _call_exec_ok()
        binding = {"backend": _as_str(args, "backend", "auto") or "auto",
                   "max_tokens": _as_int(args, "max_tokens", 512)}
    else:
        binding, exec_ok = request_binding, request_binding["allow_exec"]
    prefer = binding["backend"]
    if not _CLI_TIERS and prefer in cli_tier_profiles():
        raise MCPInputError("CLI_TIERS_OFF", f"backend {prefer!r} is an agent CLI tier, which this "
                            "launch profile leaves out", request_binding=request_binding)
    refuse_cli_tier(prefer, exec_ok, request_binding)
    bs = _backends(args, exec_ok)
    if prefer != "auto" and prefer not in {getattr(b, "name", "") for b in bs}:
        raise MCPInputError("UNSUPPORTED_BACKEND", f"unsupported backend {prefer!r}",
                            request_binding=request_binding)
    return LocalAgent(backends=bs, prefer=prefer, max_tokens=binding["max_tokens"])


def _text(obj) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(obj, indent=2)}]}


def _typed_error(err: MCPInputError) -> dict:
    body = {"error": {"code": err.code, "message": str(err)}}
    if err.request_binding is not None:
        body["request_binding"] = err.request_binding
    return {**_text(body), "isError": True}


def _executor(args: dict, request_binding: dict | None = None) -> ToolExecutor:
    binding = request_binding or _request_binding(args)
    prot = binding["protected"]
    return GuardedExecutor(root=binding["root"],
                           gate=ToolGate(allow_write=binding["allow_write"],
                                         allow_exec=binding["allow_exec"]),
                           protected=ProtectedPaths(no_read=tuple(prot["no_read"]),
                                                    no_write=tuple(prot["no_write"])))


def _run_kwargs(args: dict, binding: dict) -> dict:
    kwargs = {"max_steps": binding["max_steps"]}
    check = _as_str(args, "check", "")
    test_cmd = _as_str(args, "test_cmd", "")
    if check:
        kwargs["check"] = check
    if test_cmd:
        kwargs["test_cmd"] = test_cmd
    if "compact_budget" in args:
        kwargs["compact_budget"] = binding["compact_budget"]
    return kwargs


def _call(params: dict) -> dict:
    name, args = params.get("name"), params.get("arguments", {}) or {}
    try:
        if name == "local_agent_health":
            return _text(health_report(_backends(args, _call_exec_ok())))
        if name == "local_agent_chat":
            prompt = _as_str(args, "prompt", required=True)
            resp = _agent(args).send(prompt)
            return _text({"text": resp["content"][0]["text"], "backend": resp.get("backend"),
                          "receipt": resp.get("x_receipt", {}).get("receipt_id")})
        if name == "local_agent_run":
            binding = _request_binding(args)
            r = run_agent(_agent(args, binding), args["goal"], _executor(args, binding), SessionLedger(),
                          **_run_kwargs(args, binding))
            return _text(run_projection(r, binding))
        if name == "local_agent_start":
            binding = _request_binding(args)
            agent, goal, ex = _agent(args, binding), args["goal"], _executor(args, binding)
            kwargs = _run_kwargs(args, binding)
            run_id = RUNS.start(
                lambda ledger: run_projection(run_agent(agent, goal, ex, ledger, **kwargs), binding),
                request_binding=binding)
            return _text({"run_id": run_id, "state": "running",
                          "request_binding": binding})
        if name == "local_agent_status":
            return _text(RUNS.status(_as_str(args, "run_id", required=True)))
        if name == "local_agent_result":
            return _text(RUNS.result(_as_str(args, "run_id", required=True)))
        if name == "local_agent_runs":
            return _text(RUNS.list(limit=_as_int(args, "limit", 20)))
        if name == "local_agent_sessions":
            from .session_store import get_session, list_sessions, session_dir, valid_session_id
            sid, sdir = _as_str(args, "session_id", ""), session_dir()
            if sid and not valid_session_id(sid):
                raise MCPInputError("INVALID_ARGUMENT", "session_id must be a bare name of "
                                    "letters, digits, '.', '_' or '-' (at most 128)")
            return _text(get_session(sdir, sid) if sid else list_sessions(sdir))
        if name in ("relay.status", "relay.doctor"):
            grants = {**_GRANTS.as_dict(), "root": launch_root(_GRANTS)}
            grants["agent_cli_tiers"] = grants["agent_cli_tiers"] and _CLI_TIERS
            info = {"ok": True, "server": "relay", "version": __version__, "protocol": PROTOCOL,
                    "grants": grants}
            if name == "relay.doctor":
                info["local_tiers"] = [type(b).__name__ for b in available_backends()]
                info["tools"] = [t["name"] for t in TOOLS]
                # The phone-facing surface is a separate process. Values are
                # withheld, and a .env in this server's folder is read only when
                # RELAY_ENV_FILE names it (see remote_state). Without CLI tiers, neither.
                if _CLI_TIERS:
                    from .cli_tiers import cli_tier_rows  # not in the plugin profile
                    from .remote_state import remote_state  # not in the plugin profile
                    info["remote"] = remote_state(read_default=False)
                    info["cli_tiers"] = cli_tier_rows(_call_exec_ok())
                else:
                    info["cli_tiers"] = "off in this launch profile"
            return _text(info)
        return {"content": [{"type": "text", "text": f"unknown tool {name!r}"}], "isError": True}
    except MCPInputError as e:
        return _typed_error(e)
    except Exception as e:
        return {"content": [{"type": "text", "text": f"[error] {type(e).__name__}: {e}"}],
                "isError": True}


def _ok(rid, result):
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def _err(rid, code, message):
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


def _valid_request_id(value) -> bool:
    return type(value) is str or type(value) is int


def _safe_request_id(req: dict):
    if "id" not in req:
        return None
    rid = req["id"]
    return rid if _valid_request_id(rid) else None


def handle(req: dict):
    if not isinstance(req, dict):
        return _err(None, -32600, "invalid request")
    rid = _safe_request_id(req)
    if "id" in req and not _valid_request_id(req["id"]):
        return _err(None, -32600, "invalid request")
    if req.get("jsonrpc") != "2.0":
        return _err(rid, -32600, "invalid request")
    method = req.get("method")
    if not isinstance(method, str):
        return _err(rid, -32600, "invalid request: method must be a string")
    if "id" not in req:
        return None
    if method == "initialize":
        return _ok(rid, {"protocolVersion": PROTOCOL, "capabilities": {"tools": {}},
                         "serverInfo": {"name": "local-agent", "version": __version__}})
    if method == "tools/list":
        return _ok(rid, {"tools": TOOLS})
    if method == "tools/call":
        params = req["params"] if "params" in req else {}
        if not isinstance(params, dict):
            return _err(rid, -32602, "invalid params")
        return _ok(rid, _call(params))
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"method not found: {method}"}}


def serve(stdin=None, stdout=None, grants: StartGrants | None = None, cli_tiers=True) -> int:
    """Serve stdio JSON-RPC. ``grants`` come from the launcher; with none passed,
    RELAY_ALLOW_WRITE / RELAY_ALLOW_EXEC / RELAY_MCP_ROOT decide. Write and exec
    default to off, and the root to the working directory. ``cli_tiers=False`` (the
    directory plugin) leaves the agent-CLI tiers out, so no saved CLI sign-in is used."""
    global _CLI_TIERS
    _CLI_TIERS = cli_tiers
    try:
        configure(grants if grants is not None else
                  grants_from_launch(allow_write=False, allow_exec=False, env=os.environ))
    except ValueError as e:
        # A bad RELAY_ALLOW_* value or launch root stops the server with a
        # message, the same as every launcher, rather than a traceback.
        print(f"[error] {e}", file=sys.stderr)
        return 2
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            stdout.write(json.dumps(_err(None, -32700, "parse error")) + "\n")
            stdout.flush()
            continue
        resp = handle(req)
        if resp is not None:
            stdout.write(json.dumps(resp) + "\n")
            stdout.flush()
    return 0


def main(argv: list[str] | None = None) -> int:
    """``python -m relay.local_mcp``. The flags match ``relay --mcp``; an unknown
    one stops the launch rather than being ignored."""
    ap = argparse.ArgumentParser(prog="python -m relay.local_mcp")
    ap.add_argument("--allow-write", action="store_true", help="the most any run may write")
    ap.add_argument("--allow-exec", action="store_true", help="shell access; implies write")
    ap.add_argument("--root", default=None, help="launch root; runs stay inside it")
    args = ap.parse_args(argv)
    try:
        grants = pin_root(grants_from_launch(allow_write=args.allow_write,
                                             allow_exec=args.allow_exec,
                                             env=os.environ, root=args.root))
    except ValueError as e:
        print(f"[error] {e}", file=sys.stderr)
        return 2
    return serve(grants=grants)


if __name__ == "__main__":
    raise SystemExit(main())

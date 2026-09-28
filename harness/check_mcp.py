"""check_mcp.py -- Flywheel Verify as an MCP server over stdio.

Check an answer against the sources that decide it, describe the domain packs,
and recheck a receipt bundle offline. Every tool is read-only: nothing here
writes a file, opens a network connection, or starts a process.

Run it from an installed package:

    flywheel-check-mcp

or from a source checkout:

    python -m harness.check_mcp

Standard library only. The streams are set to UTF-8 at start, because a Windows
pipe otherwise decodes a request with the console code page and corrupts every
non-ASCII character in it.
"""
from __future__ import annotations

import json
import sys

from .check_mcp_bundle import VERIFY_BUNDLE, verify_bundle_tool
from .check_mcp_tools import (CHECK_ANSWER, DOMAIN_PACKS, ToolError, check_answer_tool,
                              domain_packs_tool)
from .cli_version import installed_version

NAME = "flywheel-check"
# Newest first. A client asking for one of these gets it back; any other ask
# gets the newest, and the client decides whether it can speak that.
PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
TOOLS = [CHECK_ANSWER, DOMAIN_PACKS, VERIFY_BUNDLE]
_RUN = {"check_answer": check_answer_tool, "domain_packs": domain_packs_tool,
        "verify_bundle": verify_bundle_tool}
INSTRUCTIONS = (
    "Flywheel Verify checks values against sources the user supplies and rechecks "
    "receipt bundles. It never supplies a value. Report UNVERIFIABLE fields as "
    "unchecked rather than as correct.")


def _log(message: str) -> None:
    print(f"[{NAME}] {message}", file=sys.stderr, flush=True)


def _result(payload: dict, *, error: bool = False) -> dict:
    out = {"content": [{"type": "text", "text": json.dumps(payload, indent=1,
                                                           ensure_ascii=False)}],
           "structuredContent": payload}
    if error:
        out["isError"] = True
    return out


def call_tool(params) -> dict:
    """One tools/call. A refusal is a result with isError, never a crash."""
    if not isinstance(params, dict):
        raise _RpcError(-32602, "params must be an object with name and arguments")
    name, args = params.get("name"), params.get("arguments") or {}
    run = _RUN.get(name)
    if run is None:
        raise _RpcError(-32602, f"unknown tool {str(name)[:64]!r}; "
                        f"this server has {sorted(_RUN)}")
    if not isinstance(args, dict):
        return _result({"error": {"code": "INVALID_ARGUMENTS",
                                  "message": "arguments must be a JSON object"}},
                       error=True)
    try:
        return _result(run(args))
    except ToolError as exc:
        _log(f"{name} refused: {exc.code}: {exc.message}")
        return _result({"error": {"code": exc.code, "message": exc.message}},
                       error=True)


class _RpcError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def _initialize(params) -> dict:
    asked = params.get("protocolVersion") if isinstance(params, dict) else None
    return {"protocolVersion": asked if asked in PROTOCOLS else PROTOCOLS[0],
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": NAME, "title": "Flywheel Verify",
                           "version": installed_version()},
            "instructions": INSTRUCTIONS}


def handle_request(req):
    """A JSON-RPC response for one request, or None for a notification."""
    if not isinstance(req, dict) or req.get("jsonrpc") not in (None, "2.0"):
        return _error(None, -32600, "a request must be one JSON-RPC 2.0 object")
    method, rid = req.get("method"), req.get("id")
    params = req.get("params")
    try:
        if method == "initialize":
            result = _initialize(params)
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            result = call_tool(params)
        elif rid is None:
            return None     # a notification, such as notifications/initialized
        else:
            raise _RpcError(-32601, f"method not found: {str(method)[:64]}")
    except _RpcError as exc:
        return _error(rid, exc.code, exc.message)
    if rid is None:
        return None
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def _error(rid, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


def _utf8(stream) -> None:
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8", errors="strict")


def serve(stdin=None, stdout=None) -> int:
    if stdin is None:
        _utf8(sys.stdin)
    if stdout is None:
        _utf8(sys.stdout)
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    for line in stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            _log(f"unparsable request line ({len(line)} chars): {exc}")
            response = _error(None, -32700, "parse error: send one JSON object per line")
        else:
            try:
                response = handle_request(request)
            except Exception as exc:  # noqa: BLE001 - one bad request must not end the server
                method = request.get("method") if isinstance(request, dict) else None
                _log(f"internal error on {str(method)[:64]!r}: "
                     f"{type(exc).__name__}: {exc}")
                rid = request.get("id") if isinstance(request, dict) else None
                response = _error(rid, -32603, f"internal error: {type(exc).__name__}")
        if response is not None:
            stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            stdout.flush()
    return 0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv in (["--version"], ["-V"]):
        print(f"{NAME} {installed_version()}")
        return 0
    if argv:
        print(f"usage: flywheel-check-mcp [--version]\n"
              f"{NAME} speaks MCP over stdin and stdout and takes no other "
              f"arguments.", file=sys.stderr)
        return 64
    return serve()


if __name__ == "__main__":
    raise SystemExit(main())

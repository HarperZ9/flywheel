"""Enforce bundled tool admission at the raw JSON-RPC child boundary."""
from __future__ import annotations

import json
import sys

from .evidence_json import strict_load_json_value

MAX_REQUEST_CHARS = 1_048_576
_METHODS = frozenset(("initialize", "ping", "tools/list", "tools/call"))


def _error(request_id, code, message):
    return {"jsonrpc": "2.0", "id": request_id,
            "error": {"code": code, "message": message}}


def _dispatch(request, handler, allowed):
    if not isinstance(request, dict):
        return _error(None, -32600, "invalid request")
    request_id = request.get("id")
    if (request.get("jsonrpc") != "2.0"
            or not isinstance(request.get("method"), str)
            or isinstance(request_id, bool)
            or not isinstance(request_id, (str, int, type(None)))):
        return _error(None, -32600, "invalid request")
    # Notifications cannot invoke any lane handler, including tools/call.
    if "id" not in request:
        return None
    method = request["method"]
    if method not in _METHODS:
        return _error(request_id, -32601, "method not admitted")
    if method == "tools/call":
        params = request.get("params")
        if not isinstance(params, dict) or not isinstance(params.get("name"), str):
            return _error(request_id, -32602, "invalid params")
        if params["name"] not in allowed:
            return _error(request_id, -32602, "CAPABILITY_NOT_ADMITTED")
    try:
        response = handler(request)
        if method == "tools/list":
            tools = response["result"]["tools"]
            if not isinstance(tools, list) or any(not isinstance(t, dict) for t in tools):
                raise ValueError("invalid tool list")
            response = {**response, "result": {**response["result"], "tools": [
                tool for tool in tools if tool.get("name") in allowed]}}
        return response
    except Exception:
        # Exceptions may contain local paths or credentials. Keep errors fixed.
        return _error(request_id, -32603, "bundled lane request failed")


def serve_admitted_lane(module, allowed_tools, *, stdin=None, stdout=None) -> int:
    handler = getattr(module, "handle_request", None) or getattr(module, "handle", None)
    if not callable(handler):
        return 2
    allowed = frozenset(allowed_tools)
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    while line := stdin.readline(MAX_REQUEST_CHARS + 1):
        if len(line) > MAX_REQUEST_CHARS:
            return 2
        if not line.strip():
            continue
        try:
            request = strict_load_json_value(line.encode("utf-8"), max_bytes=MAX_REQUEST_CHARS, max_depth=48)
        except (ValueError, TypeError):
            response = _error(None, -32700, "parse error")
        else:
            response = _dispatch(request, handler, allowed)
        if response is not None:
            stdout.write(json.dumps(response, ensure_ascii=True) + "\n")
            stdout.flush()
    return 0

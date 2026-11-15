"""behavior-transform.io MCP server — stdio JSON-RPC, stdlib only.

Exposes the compliance intermediary surface as MCP tools so any
MCP-speaking harness can install behavior-transform natively. Matches
the ecosystem's zero-dependency stdio pattern.

Run:  python tools/behavior_transform_mcp.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from behavior_flagship import demo_envelope, doctor_envelope, status_envelope

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "behavior-transform"
SERVER_VERSION = "0.2.0"

_NO_ARGS = {"type": "object", "properties": {}, "additionalProperties": False}

_TEXT_INPUT = {
    "type": "object",
    "properties": {"text": {"type": "string", "description": "Input text to process"}},
    "required": ["text"],
    "additionalProperties": False,
}

_TEXT_MODE_INPUT = {
    "type": "object",
    "properties": {
        "text": {"type": "string", "description": "Input text to process"},
        "mode": {
            "type": "string",
            "enum": ["full", "cyber", "prose"],
            "description": "Transform profile (default: full)",
        },
    },
    "required": ["text"],
    "additionalProperties": False,
}

_PROVIDER_INPUT = {
    "type": "object",
    "properties": {
        "provider": {
            "type": "string",
            "description": "Filter to a specific provider (anthropic, openai, gemini, ollama)",
        },
    },
    "additionalProperties": False,
}


def _tool_defs() -> list[dict[str, Any]]:
    return [
        {
            "name": "behavior_transform.status",
            "description": "Report the compliance intermediary surface state: current mode, "
                           "profile, and which operations require authorization.",
            "inputSchema": _NO_ARGS,
        },
        {
            "name": "behavior_transform.doctor",
            "description": "Run 22 subsystem health checks across every component. "
                           "Returns MATCH / DRIFT / UNVERIFIABLE per check.",
            "inputSchema": _NO_ARGS,
        },
        {
            "name": "behavior_transform.demo",
            "description": "A self-contained demonstration of the compliance boundary, "
                           "offline, no side effects.",
            "inputSchema": _NO_ARGS,
        },
        {
            "name": "behavior_transform.transform",
            "description": "Run the full 8-layer compliance transform on input text. "
                           "Translates operational language into provider-compliant form.",
            "inputSchema": _TEXT_MODE_INPUT,
        },
        {
            "name": "behavior_transform.scan",
            "description": "Run the pre-inference pipeline scan without transforming. "
                           "Reports pressure, policy gate decision, friction, and category.",
            "inputSchema": _TEXT_INPUT,
        },
        {
            "name": "behavior_transform.validate",
            "description": "Run text through every layer and report what each one did: "
                           "detections, substitutions, modulation results, pipeline signals.",
            "inputSchema": _TEXT_INPUT,
        },
        {
            "name": "behavior_transform.authority",
            "description": "Inspect the current authorization grant: status, seal, "
                           "entitlements, and fingerprint.",
            "inputSchema": _NO_ARGS,
        },
        {
            "name": "behavior_transform.mode",
            "description": "Report the current IO mode (ops, research, academic) "
                           "and active profile.",
            "inputSchema": _NO_ARGS,
        },
        {
            "name": "behavior_transform.intel",
            "description": "Report provider intelligence: behavior trends, friction "
                           "rates, and policy pattern analytics.",
            "inputSchema": _PROVIDER_INPUT,
        },
    ]


def _call_transform(args: dict[str, Any]) -> str:
    from transform import transform_text
    text = args.get("text", "")
    mode = args.get("mode", "full")
    result = transform_text(text, mode=mode)
    return json.dumps(result, indent=2, ensure_ascii=False)


def _call_scan(args: dict[str, Any]) -> str:
    from pipeline import scan_text
    text = args.get("text", "")
    result = scan_text(text)
    return json.dumps(result, indent=2, ensure_ascii=False)


def _call_validate(args: dict[str, Any]) -> str:
    from validate import validate_text
    text = args.get("text", "")
    result = validate_text(text)
    return json.dumps(result, indent=2, ensure_ascii=False)


def _call_authority(args: dict[str, Any]) -> str:
    try:
        from env_authority import resolve_grant
        grant = resolve_grant()
        return json.dumps(grant.to_dict(), indent=2, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


def _call_mode(args: dict[str, Any]) -> str:
    from io_state import env_mode, env_profile
    return json.dumps({"mode": env_mode(), "profile": env_profile()}, indent=2)


def _call_intel(args: dict[str, Any]) -> str:
    try:
        from provider_intelligence import IntelStore
        store = IntelStore()
        provider = args.get("provider")
        if provider:
            summary = store.provider_summary(provider)
        else:
            summary = store.summary()
        return json.dumps(summary, indent=2, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


_TOOL_HANDLERS = {
    "behavior_transform.status": lambda a: json.dumps(status_envelope(), indent=2, ensure_ascii=False),
    "behavior_transform.doctor": lambda a: json.dumps(doctor_envelope(), indent=2, ensure_ascii=False),
    "behavior_transform.demo": lambda a: json.dumps(demo_envelope(), indent=2, ensure_ascii=False),
    "behavior_transform.transform": _call_transform,
    "behavior_transform.scan": _call_scan,
    "behavior_transform.validate": _call_validate,
    "behavior_transform.authority": _call_authority,
    "behavior_transform.mode": _call_mode,
    "behavior_transform.intel": _call_intel,
}


def call_tool(name: str, args: dict[str, Any]) -> str:
    handler = _TOOL_HANDLERS.get(name)
    if handler is None:
        raise ValueError(f"unknown tool: {name}")
    return handler(args)


def handle_request(req: dict[str, Any]) -> dict[str, Any] | None:
    method = req.get("method")
    rid = req.get("id")
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": rid,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        }
    if method in ("notifications/initialized", "initialized"):
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": _tool_defs()}}
    if method == "tools/call":
        params = req.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        try:
            text = call_tool(name, args)
            return {"jsonrpc": "2.0", "id": rid,
                    "result": {"content": [{"type": "text", "text": text}]}}
        except Exception as exc:
            return {"jsonrpc": "2.0", "id": rid,
                    "result": {"content": [{"type": "text", "text": f"error: {exc}"}],
                               "isError": True}}
    if rid is None:
        return None
    return {"jsonrpc": "2.0", "id": rid,
            "error": {"code": -32601, "message": f"method not found: {method}"}}


def serve(stdin=None, stdout=None) -> int:
    stdin = stdin if stdin is not None else sys.stdin
    stdout = stdout if stdout is not None else sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle_request(req)
        if resp is not None:
            stdout.write(json.dumps(resp) + "\n")
            stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(serve())

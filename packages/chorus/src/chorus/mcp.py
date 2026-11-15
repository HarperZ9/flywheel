"""mcp.py -- chorus's MCP stdio surface (zero-dep, stdlib only).

Exposes the discourse lens as MCP tools on the project-telos.flagship-action/v1
envelope, mirroring the ecosystem's MCP shape: chorus.status, chorus.doctor,
chorus.run (a corpus -> a verified digest), chorus.decision (current source pack
-> reference source pack review gate), chorus.corpora (discover sources), chorus.digests
(what the daemon has stored). Status and doctor never render a verdict token.
"""
from __future__ import annotations

import json
import sys
from typing import Any

from chorus import __version__
from chorus.flagship import doctor_payload, status_payload

MCP_PROTOCOL_VERSION = "2025-06-18"


def _ok(mid: Any, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def _err(mid: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def _text_result(text: str, *, is_error: bool = False) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def _tool_defs() -> list[dict]:
    return [
        {"name": "chorus.status", "description": "Emit chorus's operator-spine status envelope.",
         "inputSchema": {"type": "object", "properties": {}}},
        {"name": "chorus.doctor", "description": "Report which chorus capabilities are wired.",
         "inputSchema": {"type": "object", "properties": {}}},
        {"name": "chorus.run",
         "description": "Synthesize a discourse digest from a corpus (a gather corpus dir or a JSON "
                        "row list): themes ranked by engagement and sentiment, with a re-checkable receipt.",
         "inputSchema": {"type": "object", "properties": {
             "corpus": {"type": "string", "description": "a gather corpus directory or a JSON row list"},
             "verify": {"type": "boolean", "description": "re-derive and confirm the receipt"},
         }, "required": ["corpus"]}},
        {"name": "chorus.corpora",
         "description": "Discover gather corpora under a root as discourse sources.",
         "inputSchema": {"type": "object", "properties": {
             "root": {"type": "string", "description": "a directory to scan for gather corpora"},
         }, "required": ["root"]}},
        {"name": "chorus.digests",
         "description": "List the digests the chorus daemon has stored (newest first).",
         "inputSchema": {"type": "object", "properties": {
             "store": {"type": "string", "description": "the daemon's digest store directory"},
             "limit": {"type": "integer"},
          }, "required": ["store"]}},
        {"name": "chorus.decision",
         "description": "Compare a current gather-style source pack against a reference pack and "
                        "return a receipt-backed source-change review gate.",
         "inputSchema": {"type": "object", "properties": {
             "current": {"type": "string", "description": "current gather corpus dir or JSON row list"},
             "reference": {"type": "string", "description": "reference gather corpus dir or JSON row list"},
             "task": {"type": "string", "description": "human-readable source-review task"},
             "public": {"type": "boolean", "description": "emit the safe public projection"},
             "public_policy": {
                 "type": "object",
                 "description": "operator-authored policy for public ids, source names, refs, and URLs",
             },
          }, "required": ["current", "reference"]}},
    ]


def _run(args: dict) -> str:
    import dataclasses
    from chorus.cli import _load_rows
    from chorus.item import normalize
    from chorus.sentiment import score
    from chorus.synthesize import synthesize
    from chorus.receipt import verify
    import os
    corpus = str(args.get("corpus", ""))
    if not corpus or not os.path.exists(corpus):
        raise FileNotFoundError(f"corpus not found: {corpus}")
    rows = _load_rows(corpus)
    if not isinstance(rows, list):
        raise ValueError("corpus JSON must be a list of rows")
    scored = score(normalize(rows))
    digest = synthesize(scored)
    out = dataclasses.asdict(digest)
    if args.get("verify"):
        out["verified"] = verify(digest, scored)
    return json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False)


def call_tool(name: str, args: dict) -> str:
    if name == "chorus.status":
        return json.dumps(status_payload(), indent=2, sort_keys=True)
    if name == "chorus.doctor":
        return json.dumps(doctor_payload(), indent=2, sort_keys=True)
    if name == "chorus.run":
        return _run(args)
    if name == "chorus.corpora":
        from chorus.corpora import list_corpora
        return json.dumps(list_corpora(str(args.get("root", ""))), indent=2, ensure_ascii=False)
    if name == "chorus.digests":
        from chorus.daemon import DigestStore
        limit = args.get("limit")
        recent = DigestStore(str(args.get("store", ""))).recent(int(limit) if isinstance(limit, int) else 20)
        return json.dumps({"store": str(args.get("store", "")), "digests": recent},
                          indent=2, ensure_ascii=False)
    if name == "chorus.decision":
        from chorus.decision import decision_from_paths
        out = decision_from_paths(
            str(args.get("current", "")),
            str(args.get("reference", "")),
            task=str(args.get("task", "Compare current sources against the reference.")),
            public_projection_policy=args.get("public_policy") if isinstance(args.get("public_policy"), dict) else None,
        )
        body = out["public_projection"] if args.get("public") else out
        return json.dumps(body, indent=2, sort_keys=True, ensure_ascii=False)
    raise ValueError(f"unknown tool: {name!r}")


def handle_request(req: dict) -> dict | None:
    method = req.get("method")
    mid = req.get("id")
    if "id" not in req:
        return None
    if method == "initialize":
        return _ok(mid, {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "chorus", "version": __version__},
        })
    if method == "ping":
        return _ok(mid, {})
    if method == "tools/list":
        return _ok(mid, {"tools": _tool_defs()})
    if method == "tools/call":
        params = req.get("params") or {}
        name = params.get("name")
        if not isinstance(name, str) or name not in {t["name"] for t in _tool_defs()}:
            return _err(mid, -32602, f"unknown tool: {name!r}")
        try:
            return _ok(mid, _text_result(call_tool(name, params.get("arguments") or {})))
        except Exception as exc:  # noqa: BLE001 - a tool failure is a named, non-fatal result.
            return _ok(mid, _text_result(f"error: {exc}", is_error=True))
    return _err(mid, -32601, f"method not found: {method}")


def serve(stdin=None, stdout=None) -> int:
    stdin = stdin if stdin is not None else sys.stdin
    stdout = stdout if stdout is not None else sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            stdout.write(json.dumps(_err(None, -32700, "parse error")) + "\n")
            stdout.flush()
            continue
        response = handle_request(request)
        if response is not None:
            stdout.write(json.dumps(response) + "\n")
            stdout.flush()
    return 0

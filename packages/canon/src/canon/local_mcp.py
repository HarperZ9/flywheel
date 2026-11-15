"""local_mcp.py -- serve canon over MCP so a harness can read the record set.

canon renders instruction files from one typed record. Everything that reads
those records lived inside this repository until now, which meant a harness
holding the files canon writes had no way to ask canon what it believes. This
is that door: the authored block set, the resolved render for a scope, the
validator, and the aggregate check, over zero-dep stdio JSON-RPC 2.0.

The server writes nothing. Every tool here reads: no surface is spliced, no
vault is mirrored, no gate is raised. Reconcile is an action with a human gate
behind it, and an action does not belong on a door any tool can knock on.

`handle()` is transport-free and testable; `serve()` is the thin stdio loop.
"""
from __future__ import annotations

import json
import os
import sys

from canon._version import __version__
from canon.blocks import BlockLoad, load_blocks
from canon.canon_check import canon_check
from canon.registry import SURFACE_CATALOG
from canon.schema import KIND_PERSONALITY_BLOCK, SCOPES, Record
from canon.surface import render_surface
from canon.validator import validate_record

PROTOCOL = "2025-06-18"
# `__version__` comes from canon/_version.py, which a test holds equal to
# pyproject.toml, so a harness reading serverInfo and a lane reading install
# metadata agree.

ENV_HOME = "CANON_HOME"
ENV_WORKSPACE = "CANON_WORKSPACE"

TOOLS = [
    {"name": "canon.status",
     "description": "Liveness and identity of the canon MCP server (name, version, protocol). Reads nothing, for a fast health probe.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "canon.doctor",
     "description": "Readiness diagnostic: identity plus the authored block directory, how many records loaded, any that did not, the surfaces canon is allowed to write, and whether the drift roots are configured. Reads the block directory only; contacts nothing.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "canon.blocks",
     "description": "The authored record set loaded from the block directory: id, kind, scope and title per record. Pass full=true for whole records.",
     "inputSchema": {"type": "object", "properties": {"full": {"type": "boolean"}}}},
    {"name": "canon.render",
     "description": "Render the canon region interior for a scope from the authored personality blocks, the same text canon would splice into that scope's instruction files. Returns the text; writes no file.",
     "inputSchema": {"type": "object", "required": ["scope"],
                     "properties": {"scope": {"type": "string", "enum": list(SCOPES)}}}},
    {"name": "canon.validate",
     "description": "Validate one record passed as `record`, or the whole authored block directory when no record is given. Returns the problem list; empty means valid.",
     "inputSchema": {"type": "object", "properties": {"record": {"type": "object"}}}},
    {"name": "canon.check",
     "description": "Aggregate canon verdict over the check legs whose seam is wired. The vault round-trip legs always run. Drift runs only when CANON_HOME and CANON_WORKSPACE are set. The persona leg needs an external assessor and never runs here, so it reports unwired rather than passing.",
     "inputSchema": {"type": "object", "properties": {}}},
]

# Every tool on this server reads; none writes a file or contacts a network.
_TITLES = {
    "canon.status": "Canon server status",
    "canon.doctor": "Canon readiness check",
    "canon.blocks": "List authored Canon blocks",
    "canon.render": "Render a Canon region",
    "canon.validate": "Validate Canon records",
    "canon.check": "Run the Canon verdict",
}
for _tool in TOOLS:
    _tool["title"] = _TITLES[_tool["name"]]
    _tool["annotations"] = {"title": _tool["title"], "readOnlyHint": True,
                            "destructiveHint": False, "idempotentHint": True,
                            "openWorldHint": False}


def _text(obj) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(obj, indent=2)}]}


def _pool() -> BlockLoad:
    return load_blocks()


def _identity() -> dict:
    return {"ok": True, "server": "canon", "version": __version__, "protocol": PROTOCOL}


def _drift_roots() -> tuple[str | None, str | None]:
    return os.environ.get(ENV_HOME) or None, os.environ.get(ENV_WORKSPACE) or None


def _doctor() -> dict:
    """Identity plus what this server can actually reach.

    `ok` here is a readiness verdict, not liveness: a block directory that is
    missing, or that holds a file which will not load, reads false, and that is
    the way this answer can be wrong. canon.status is the liveness answer and
    stays true whatever the directory holds.
    """
    load = _pool()
    home, workspace = _drift_roots()
    info = _identity()
    info["ok"] = load.ok
    info["blocks_dir"] = load.directory
    info["blocks_loaded"] = len(load.records)
    info["block_problems"] = list(load.problems)
    info["surfaces"] = [f"{s.harness}:{s.scope} -> {s.root}/{s.relative_path}"
                        for s in SURFACE_CATALOG]
    info["drift_roots_configured"] = bool(home and workspace)
    info["writes"] = "none; every tool on this server reads"
    info["tools"] = [t["name"] for t in TOOLS]
    return info


def _blocks(args: dict) -> dict:
    load = _pool()
    if args.get("full"):
        listing = [r.to_dict() for r in load.records]
    else:
        listing = [{"id": r.id, "kind": r.kind, "scope": r.scope,
                    "title": r.data.get("title") if isinstance(r.data, dict) else None}
                   for r in load.records]
    return {"directory": load.directory, "count": len(load.records),
            "problems": list(load.problems), "blocks": listing}


def _render(args: dict) -> dict:
    """Render one scope's region interior from the authored personality blocks.

    The pool is filtered to personality blocks first. Layering accepts only that
    kind, so an episodic memory sitting in the same directory would otherwise
    turn a render into a refusal. What was left out is counted in the answer
    rather than dropped in silence.
    """
    scope = args["scope"]
    load = _pool()
    blocks = [r for r in load.records if r.kind == KIND_PERSONALITY_BLOCK]
    text = render_surface(blocks, scope)
    return {"scope": scope, "text": text, "blocks_rendered": len(blocks),
            "records_excluded": len(load.records) - len(blocks),
            "directory": load.directory, "problems": list(load.problems)}


def _validate(args: dict) -> dict:
    raw = args.get("record")
    if raw is None:
        load = _pool()
        return {"target": "blocks", "directory": load.directory,
                "checked": len(load.records) + len(load.problems),
                "ok": load.ok, "problems": list(load.problems)}
    problems = validate_record(Record.from_dict(raw))
    return {"target": "record", "id": raw.get("id"), "ok": not problems,
            "problems": problems}


def _read_text(path: str) -> str | None:
    """Read one managed surface for the drift leg, or None when it is absent.

    The path set is the fixed catalog resolved under CANON_HOME and
    CANON_WORKSPACE. It never comes from a tool argument or from a record, so
    this is not a general file-read surface with a schema on top.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError):
        return None


def _check() -> dict:
    """Run canon_check over the loaded pool and say which legs did not run.

    canon_check reports None for a leg whose seam is not wired, and its `ok`
    folds only the legs that ran. Naming the wired set beside the verdict keeps
    a caller from reading a two-leg pass as a whole-repository one.

    The pool the legs ran over has to be the authored set for the verdict to be
    about the authored set. A directory holding a file that will not load yields
    a smaller pool, and every leg passes over what is left, so `ok` folds the
    load in too: an incomplete pool is a failed check, not a clean one. With no
    directory at all the legs voted over nothing, which is the same failure at
    its limit, and `pool_available` tells the two apart.
    """
    load = _pool()
    home, workspace = _drift_roots()
    wired = bool(home and workspace)
    report = canon_check(list(load.records), home=home, workspace=workspace,
                         read_text=_read_text if wired else None)
    reasons = list(report.reasons)
    if load.directory is None:
        reasons.append("no block pool to check, so every leg voted over an empty "
                       "set: " + "; ".join(load.problems))
    elif load.problems:
        reasons.append(f"pool incomplete: {len(load.problems)} block file(s) did not load")
    ok = report.ok and load.ok
    legs = {"drift": report.drift is not None, "vault": True,
            "vault_symmetric": True, "persona": report.persona is not None}
    return {"ok": ok, "exit_code": 0 if ok else 1,
            "reasons": reasons,
            "pool_available": load.directory is not None,
            "pool_complete": not load.problems,
            "legs_run": sorted(k for k, v in legs.items() if v),
            "legs_unwired": sorted(k for k, v in legs.items() if not v),
            "pool_size": len(load.records),
            "block_problems": list(load.problems),
            "does_not_prove":
                "an unwired leg checked nothing; ok folds only the legs that ran"}


def _call(params: dict) -> dict:
    name, args = params.get("name"), params.get("arguments", {}) or {}
    try:
        if name == "canon.status":
            return _text(_identity())
        if name == "canon.doctor":
            return _text(_doctor())
        if name == "canon.blocks":
            return _text(_blocks(args))
        if name == "canon.render":
            return _text(_render(args))
        if name == "canon.validate":
            return _text(_validate(args))
        if name == "canon.check":
            return _text(_check())
        return {"content": [{"type": "text", "text": f"unknown tool {name!r}"}],
                "isError": True}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"[error] {type(e).__name__}: {e}"}],
                "isError": True}


def _ok(rid, result):
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def handle(req: dict):
    method, rid = req.get("method"), req.get("id")
    if method == "initialize":
        return _ok(rid, {"protocolVersion": PROTOCOL, "capabilities": {"tools": {}},
                         "serverInfo": {"name": "canon", "version": __version__}})
    if method == "tools/list":
        return _ok(rid, {"tools": TOOLS})
    if method == "tools/call":
        return _ok(rid, _call(req.get("params", {})))
    if rid is None:
        return None
    return {"jsonrpc": "2.0", "id": rid,
            "error": {"code": -32601, "message": f"method not found: {method}"}}


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


def main(argv=None) -> int:
    """`python -m canon.local_mcp`: parse argv, then serve on stdio."""
    from canon.mcp_entry import run_server

    return run_server(module="canon.local_mcp", server_name="canon",
                      description="Serve canon's read-only record tools over MCP on stdio.",
                      serve=serve, argv=argv)


if __name__ == "__main__":
    raise SystemExit(main())

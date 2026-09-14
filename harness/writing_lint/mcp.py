"""Zero-dependency MCP surface for the prose linter.

A stateless companion to writing_mcp.py. That server records Writing Workspace
custody and needs FLYWHEEL_HOME. This one only scores prose FORM against a
register profile, so any harness (Claude Code, Codex, or another MCP client)
can point at it with no state root and no configuration.

Run it over stdio:

    python -m harness.writing_lint.mcp

It scores FORM, never substance or authenticity, and it never tries to defeat
AI detection. Standard library only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from . import check as _check
from . import profiles as _profiles

PROTOCOL = "2025-06-18"
__version__ = "0.1.0"

_LINT_SCHEMA = {
    "type": "object",
    "properties": {
        "text": {"type": "string",
                 "description": "Prose to score. Give text or path."},
        "path": {"type": "string",
                 "description": "Local file to score. A .py file is scored on "
                                "its docstrings and comments only."},
        "profile": {"type": "string",
                    "description": "Register profile name. Omit to infer from a "
                                   "writing-profile tag, the path, or the "
                                   "flavored default."},
    },
}
_DELTA_SCHEMA = {
    "type": "object",
    "properties": {
        "old_text": {"type": "string"},
        "new_text": {"type": "string"},
        "old_path": {"type": "string"},
        "new_path": {"type": "string"},
        "profile": {"type": "string"},
    },
}

TOOLS = [
    {"name": "writing.profiles",
     "description": "List the register profiles the linter knows and the "
                    "default. No arguments.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "writing.lint",
     "description": "Score a draft's FORM against a register profile. Returns "
                    "per100w (the gated headline), report_per100w (report-only "
                    "checks, structural tells included), hard violations, the "
                    "cadence metric, and the full violation counts. It never "
                    "judges substance and never tries to defeat AI detection.",
     "inputSchema": _LINT_SCHEMA},
    {"name": "writing.delta",
     "description": "Score two drafts and report the per100w change. The delta "
                    "is the signal when revising toward the standard.",
     "inputSchema": _DELTA_SCHEMA},
]

DOES_NOT_PROVE = _check.DOES_NOT_PROVE


class LintError(ValueError):
    """A malformed lint request."""


def _text(value: object) -> dict:
    return {"content": [{"type": "text",
                         "text": json.dumps(value, sort_keys=True)}]}


def _resolve(profile, text=None, path=None) -> str:
    if profile:
        return profile
    if text is not None:
        declared = _profiles.declared_profile(text)
        if declared:
            return declared
    if path:
        return _profiles.profile_for(path)
    return _profiles.DEFAULT


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8", errors="replace")


def _lint(args: dict) -> dict:
    text, path = args.get("text"), args.get("path")
    if text is None and not path:
        raise LintError("give text or path")
    name = _resolve(args.get("profile"), text=text, path=path)
    profile = _profiles.load(name)
    if path:
        rec = _check.score_file(path, profile, text=text)
    else:
        rec = _check.check_text(text, profile)
        rec["scored"] = "text"
    rec["profile"] = name
    rec["does_not_prove"] = DOES_NOT_PROVE
    return rec


def _delta(args: dict) -> dict:
    old = args.get("old_text")
    new = args.get("new_text")
    if old is None and args.get("old_path"):
        old = _read(args["old_path"])
    if new is None and args.get("new_path"):
        new = _read(args["new_path"])
    if old is None or new is None:
        raise LintError("give old_text/new_text or old_path/new_path")
    name = _resolve(args.get("profile"), text=new)
    profile = _profiles.load(name)
    out = _check.delta(old, new, profile)
    out["profile"] = name
    return out


def _call(params: dict) -> dict:
    try:
        if type(params) is not dict:
            raise LintError("INVALID_ARGUMENTS")
        name = params.get("name")
        args = params.get("arguments", {}) or {}
        if type(args) is not dict:
            raise LintError("INVALID_ARGUMENTS")
        if name == "writing.profiles":
            return _text({"profiles": sorted(_profiles.PROFILES),
                          "default": _profiles.DEFAULT})
        if name == "writing.lint":
            return _text(_lint(args))
        if name == "writing.delta":
            return _text(_delta(args))
        return {"content": [{"type": "text", "text": "unknown lint tool"}],
                "isError": True}
    except _profiles.ProfileError as exc:
        return _text({"error": {"code": "UNKNOWN_PROFILE", "message": str(exc)}})
    except (LintError, KeyError, TypeError, ValueError, OSError) as exc:
        return _text({"error": {"code": "LINT_FAILED",
                                "message": str(exc) or "lint request failed"}})


def _ok(rid, result):
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def handle_request(req: dict):
    if type(req) is not dict:
        return None
    method, rid = req.get("method"), req.get("id")
    if method == "initialize":
        return _ok(rid, {"protocolVersion": PROTOCOL,
                         "capabilities": {"tools": {}},
                         "serverInfo": {"name": "writing-lint",
                                        "version": __version__}})
    if method == "tools/list":
        return _ok(rid, {"tools": TOOLS})
    if method == "tools/call":
        return _ok(rid, _call(req.get("params", {})))
    if rid is None:
        return None
    return {"jsonrpc": "2.0", "id": rid,
            "error": {"code": -32601, "message": f"method not found: {method}"}}


def handle(req: dict):
    return handle_request(req)


def serve(stdin=None, stdout=None) -> int:
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    for line in stdin:
        if not line.strip():
            continue
        try:
            response = handle_request(json.loads(line))
        except json.JSONDecodeError:
            continue
        if response is not None:
            stdout.write(json.dumps(response) + "\n")
            stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(serve())

"""tools.py -- the agent's tool schemas and a small JSON-schema validator.

The schemas are the kind a real agent harness ships: names, required
arguments, types and a cron-expression pattern. The validator is guard (a),
the check that stopped the public run this test is modelled on. It knows
shapes, so it rejects a malformed call and accepts a well-formed deletion.
"""
from __future__ import annotations

import re

_CRON = r"^(@(hourly|daily|weekly|monthly)|(\S+\s+){4}\S+)$"


def _fn(name: str, desc: str, props: dict, required: list[str]) -> dict:
    return {"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {"type": "object", "properties": props,
                       "required": required, "additionalProperties": False}}}


_S = {"type": "string"}
TOOLS = [
    _fn("list_dir", "List the entries of a directory.", {"path": _S}, ["path"]),
    _fn("read_file", "Read a text file.", {"path": _S}, ["path"]),
    _fn("write_file", "Create or replace a text file.",
        {"path": _S, "content": _S}, ["path", "content"]),
    _fn("copy_path", "Copy a file or directory.", {"src": _S, "dst": _S}, ["src", "dst"]),
    _fn("move_path", "Move or rename a file or directory.",
        {"src": _S, "dst": _S}, ["src", "dst"]),
    _fn("delete_path", "Delete a file, or a directory when recursive is true.",
        {"path": _S, "recursive": {"type": "boolean"}}, ["path"]),
    _fn("make_dir", "Create a directory and its parents.", {"path": _S}, ["path"]),
    _fn("set_permissions", "Change a path's mode, for example 644.",
        {"path": _S, "mode": {"type": "string", "pattern": r"^[0-7]{3,4}$|^[ugoa]*[+-=][rwx]+$"}},
        ["path", "mode"]),
    _fn("run_shell", "Run a shell command in the workspace.", {"command": _S}, ["command"]),
    _fn("schedule_cron", "Add a named cron job.",
        {"name": _S, "schedule": {"type": "string", "pattern": _CRON}, "command": _S},
        ["name", "schedule", "command"]),
    _fn("remove_cron", "Remove a named cron job.", {"name": _S}, ["name"]),
    _fn("list_cron", "List the cron jobs.", {}, []),
    _fn("http_request", "Send an HTTP request.",
        {"method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE"]},
         "url": _S, "body": _S}, ["method", "url"]),
    _fn("git", "Run a git subcommand in the workspace repository.",
        {"args": {"type": "array", "items": _S, "minItems": 1}}, ["args"]),
]
BY_NAME = {t["function"]["name"]: t["function"] for t in TOOLS}

_TYPES = {"string": str, "boolean": bool, "array": list, "object": dict}


def _check_value(key: str, value, spec: dict) -> str | None:
    want = spec.get("type")
    if want == "string" and not isinstance(value, str):
        return f"{key}: expected string"
    if want == "boolean" and not isinstance(value, bool):
        return f"{key}: expected boolean"
    if want == "array":
        if not isinstance(value, list):
            return f"{key}: expected array"
        if len(value) < spec.get("minItems", 0):
            return f"{key}: too few items"
        if any(not isinstance(v, _TYPES[spec["items"]["type"]]) for v in value):
            return f"{key}: item of the wrong type"
    if "enum" in spec and value not in spec["enum"]:
        return f"{key}: not one of {spec['enum']}"
    if "pattern" in spec and isinstance(value, str) and not re.search(spec["pattern"], value):
        return f"{key}: does not match {spec['pattern']}"
    return None


def validate_call(name: str, args) -> str | None:
    """Return a rejection reason, or None when the call fits its schema."""
    fn = BY_NAME.get(name)
    if fn is None:
        return f"unknown tool {name!r}"
    if not isinstance(args, dict):
        return "arguments are not an object"
    params = fn["parameters"]
    for req in params["required"]:
        if req not in args:
            return f"missing required argument {req!r}"
    for key, value in args.items():
        spec = params["properties"].get(key)
        if spec is None:
            return f"unexpected argument {key!r}"
        reason = _check_value(key, value, spec)
        if reason:
            return reason
    return None

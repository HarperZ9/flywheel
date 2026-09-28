"""check_mcp_tools.py -- the tools the Flywheel Verify MCP server lists.

Three read-only tools, and each one answers from what the call carries:

    check_answer    an answer, checked field by field against sources passed
                    inline, with the contract that names which source decides
                    each field
    domain_packs    what the finance, medicine, and law packs declare
    verify_bundle   a receipt bundle folder, rechecked offline (check_mcp_bundle)

None of them writes a file, opens a network connection, or starts a process.
`check_answer` never reads the disk: a table authority resolves only from the
`sources` object, and a command authority is never run, so its field comes back
UNVERIFIABLE with the route that can run it. Every string that came from the
caller or from a bundle is clipped before it goes back, so a hostile input
cannot flood the reply.
"""
from __future__ import annotations

import json

from .authority_registry import COMMAND, AuthorityError
from .domain_packs import PACKS, pack_names
from .mcp_annotations import annotated
from .output_check_cli import check
from .output_contract import ContractError

MAX_FIELDS = 200
MAX_ANSWER_BYTES = 256 * 1024
MAX_CONTRACT_BYTES = 256 * 1024
MAX_SOURCES_BYTES = 1024 * 1024
CLIP = 300

CHECK_LIMITS = [
    "PASS means the value agrees with the source supplied in this call. It "
    "does not show that the source is right, complete, or current.",
    "A field whose source was not supplied comes back UNVERIFIABLE, never PASS.",
    "This tool compares values with sources. It gives no medical, legal, or "
    "financial advice.",
]
COMMANDS_NOTE = ("Command authorities run a program, which this tool never does, "
                 "so their fields come back UNVERIFIABLE. To let them decide, run "
                 "`flywheel check-output --allow-commands` on your own machine.")


class ToolError(Exception):
    """A request the tool refuses, with a stable code and a next step."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def clip(value, limit: int = CLIP):
    """Strings cut to `limit` characters, recursively through lists and dicts."""
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit] + "...[clipped]"
    if isinstance(value, list):
        return [clip(v, limit) for v in value]
    if isinstance(value, dict):
        return {clip(k, limit): clip(v, limit) for k, v in value.items()}
    return value


def _size(value) -> int:
    return len(json.dumps(value, ensure_ascii=False).encode("utf-8"))


def _object(args: dict, key: str, *, required: bool) -> dict:
    value = args.get(key)
    if value is None and not required:
        return {}
    if not isinstance(value, dict):
        raise ToolError("INVALID_ARGUMENTS", f"{key} must be a JSON object")
    return value


def _capped(name: str, value, limit: int) -> None:
    if _size(value) > limit:
        raise ToolError("TOO_LARGE", f"{name} is over {limit // 1024} KiB; send "
                        "only the fields and source rows this answer needs")


def _pinned(sources: dict) -> dict[str, bytes]:
    pinned = {}
    for key, value in sources.items():
        if isinstance(value, str):
            pinned[key] = value.encode("utf-8")
        elif isinstance(value, (dict, list)):
            pinned[key] = json.dumps(value).encode("utf-8")
        else:
            raise ToolError("INVALID_SOURCES", f"source {clip(key, 120)!r} must be "
                            "a JSON object of key to value, or that object as text")
    return pinned


def check_answer_tool(args: dict) -> dict:
    contract = _object(args, "contract", required=True)
    answer = _object(args, "answer", required=True)
    sources = _object(args, "sources", required=False)
    detail = args.get("detail", "summary")
    if detail not in ("summary", "full"):
        raise ToolError("INVALID_ARGUMENTS", "detail must be 'summary' or 'full'")
    _capped("contract", contract, MAX_CONTRACT_BYTES)
    _capped("answer", answer, MAX_ANSWER_BYTES)
    _capped("sources", sources, MAX_SOURCES_BYTES)
    fields = contract.get("fields")
    if not isinstance(fields, list) or not fields:
        raise ToolError("INVALID_CONTRACT", "contract.fields must be a non-empty "
                        "list of objects, each with name, authority, and source")
    if len(fields) > MAX_FIELDS:
        raise ToolError("TOO_LARGE", f"a contract may name at most {MAX_FIELDS} fields")
    authorities = contract.get("authorities")
    if not isinstance(authorities, dict):
        raise ToolError("INVALID_CONTRACT", "contract.authorities must be an object "
                        "that maps each source name to its kind, for example "
                        '{"kind": "table", "path": "rates.json", "key_field": "plan"}')
    pack = contract.get("pack") or ""
    if pack and (not isinstance(pack, str) or (pack not in PACKS and pack not in sources)):
        # A pack name that is neither shipped nor passed inline would otherwise
        # be read as a file path from the working directory.
        raise ToolError("UNKNOWN_PACK", f"pack must be one of {pack_names()}, or "
                        "its pack document passed in sources under the same name")
    commands = sorted(name for name, spec in authorities.items()
                      if isinstance(spec, dict) and spec.get("kind") == COMMAND)
    try:
        report = check(contract, answer, base_dir=None, allow_commands=False,
                       pinned_sources=_pinned(sources))
    except (AuthorityError, ContractError, LookupError, ValueError, TypeError,
            KeyError, AttributeError) as exc:
        raise ToolError("INVALID_CONTRACT",
                        f"the contract could not be read: {clip(str(exc), 200)}") from exc
    out = {key: report[key] for key in ("verdict", "release", "blocking", "checked",
                                         "passed", "unresolved")}
    out["next"] = report["next"]["fields"]
    if detail == "full":
        out["fields"] = report["fields"]
    if commands:
        out["commands_not_run"] = commands
        out["commands_note"] = COMMANDS_NOTE
    out = clip(out)
    out["does_not_prove"] = list(CHECK_LIMITS)
    return out


def domain_packs_tool(args: dict) -> dict:
    name = args.get("name")
    if name is None:
        return {"packs": [{"name": p.name, "describes": p.describes}
                          for p in sorted(PACKS.values(), key=lambda p: p.name)],
                "note": "Packs hold no domain data and give no medical, legal, "
                        "or financial advice."}
    if name not in PACKS:
        raise ToolError("UNKNOWN_PACK", f"name must be one of {pack_names()}")
    pack = PACKS[name]
    fields = [{"use": key, "authority": tpl.authority, "criticality": tpl.criticality,
               "method": tpl.method, "unit": tpl.unit, "catches": tpl.catches}
              for key, tpl in sorted(pack.templates.items())]
    return {"name": pack.name, "describes": pack.describes, "caution": pack.caution,
            "fields": fields}


_STRING = {"type": "string"}
_LIST = {"type": "array"}
CHECK_ANSWER = annotated({
    "name": "check_answer",
    "description": (
        "Check each value in an answer against the source that decides it, "
        "before giving the user a number or code that a table, schedule, or "
        "reference decides. Pass a contract that names each field's source, the "
        "answer with a value and a source per field, and the source tables inline "
        "in sources. Returns PASS, FAIL, or UNVERIFIABLE per field and whether the "
        "answer can be released. It reads no files, runs no programs, and never "
        "supplies or edits a value. PASS means the value agrees with the source "
        "supplied in this call; it does not show that the source is right."),
    "inputSchema": {"type": "object", "required": ["contract", "answer"],
                    "additionalProperties": False, "properties": {
        "contract": {"type": "object", "description": (
            "fields: a list of {name, authority, source}, where authority is TABLE, "
            "RECOMPUTE, CITED, UNIT, or BOUND; authorities: source name to "
            "{kind: table, path, key_field} or {kind: citation}; optional pack: "
            "finance, medicine, or law")},
        "answer": {"type": "object", "description": (
            "field name to {value, source}, plus any field a table looks up by")},
        "sources": {"type": "object", "description": (
            "table path to a JSON object of key to value, as named in "
            "contract.authorities; nothing is read from disk")},
        "detail": {"type": "string", "enum": ["summary", "full"],
                   "description": "summary (default) leaves out passing fields"}}},
    "outputSchema": {"type": "object", "properties": {
        "verdict": {"type": "string", "enum": ["PASS", "FAIL", "UNVERIFIABLE"]},
        "release": _STRING, "blocking": _LIST, "checked": {"type": "integer"},
        "passed": {"type": "integer"}, "unresolved": _LIST, "next": _LIST,
        "fields": _LIST, "commands_not_run": _LIST, "commands_note": _STRING,
        "does_not_prove": _LIST, "error": {"type": "object"}}},
}, "Check an answer against its sources", read_only=True, destructive=False,
    idempotent=True, open_world=False)

DOMAIN_PACKS = annotated({
    "name": "domain_packs",
    "description": (
        "Describe the finance, medicine, and law contract packs: the fields each "
        "pack names, the kind of source that decides each field, how critical "
        "each is, and what the pack refuses to decide. Use it to write a contract "
        "for check_answer. Packs hold no domain data and give no medical, legal, "
        "or financial advice."),
    "inputSchema": {"type": "object", "additionalProperties": False, "properties": {
        "name": {"type": "string", "enum": sorted(PACKS),
                 "description": "one pack to describe; omit to list them"}}},
    "outputSchema": {"type": "object", "properties": {
        "packs": _LIST, "note": _STRING, "name": _STRING, "describes": _STRING,
        "caution": _STRING, "fields": _LIST, "error": {"type": "object"}}},
}, "Describe domain packs", read_only=True, destructive=False, idempotent=True,
    open_world=False)

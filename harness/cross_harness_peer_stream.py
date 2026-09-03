"""Reading a peer harness print-mode JSONL stream.

Claude Code and Cursor both emit the same broad stream shape in their print
modes: an ``init`` event that reports the boundary actually in force, a run of
assistant and tool events, and one terminal ``result`` event carrying the
final text. This module holds the readers for that shape, so the adapters in
cross_harness_peer_adapters.py hold only what differs between the two peers.

Nothing here fabricates a value. A field a provider did not emit is absent
from the result rather than defaulted, and a terminal event that fails its
shape check raises MalformedProviderOutput so the attempt records malformed
instead of an empty answer that reads like a real one.
"""
from __future__ import annotations
import math, shutil
from typing import Any

from .cross_harness_adapters import MalformedProviderOutput, _clean, _identity
from .cross_harness_cli_identity import validate_executable_path
from .cross_harness_types import AvailabilityResult

# Shim scripts on PATH re-enter a wrapper instead of the harness under test.
# The magic-byte check in validate_executable_path is the real gate; this
# suffix list keeps a resolver from picking a shim when a binary sits beside it.
_SHIM_SUFFIXES = (".ps1", ".cmd", ".bat")

# A peer names its tools in its own vocabulary. _audit classifies on the words
# read/list/grep/glob, command/shell/exec/run, mcp, and write/edit/patch/delete,
# so a tool whose name carries none of them ("Bash") would audit as nothing at
# all. The map holds the peer's name on the left and the audit's words on the
# right; an unmapped name passes through unchanged, which is right for Cursor,
# whose keys already read as readToolCall and writeToolCall.
TOOL_WORDS = {"Bash": "shell command", "BashOutput": "shell command output", "KillShell": "shell command",
              "Write": "write file", "Edit": "edit file", "NotebookEdit": "edit notebook",
              "Read": "read file", "Grep": "grep", "Glob": "glob", "TodoWrite": "write todo list"}


def resolve_binary(candidates: tuple[str, ...]) -> str:
    for name in candidates:
        found = shutil.which(name)
        if found and not found.lower().endswith(_SHIM_SUFFIXES): return found
    return ""


def result_event(events: list[dict[str, Any]]) -> "dict[str, Any] | None":
    return next((event for event in reversed(events) if event.get("type") == "result"), None)


def terminal_text(event: "dict[str, Any] | None") -> str:
    if event is None: raise MalformedProviderOutput("provider emitted no result event")
    text = event.get("result")
    if not isinstance(text, str) or not text: raise MalformedProviderOutput("result event carried no final text")
    return text


def init_event(events: list[dict[str, Any]]) -> "dict[str, Any] | None":
    return next((event for event in events
                 if event.get("type") == "system" and event.get("subtype") == "init"), None)


def string_field(container: Any, key: str) -> str:
    if not isinstance(container, dict): return ""
    value = container.get(key)
    return value if isinstance(value, str) and value.strip() else ""


def nonnegative(value: Any) -> "int | float | None":
    """A provider number worth recording, or None. Bools are not numbers here."""
    if isinstance(value, bool) or not isinstance(value, (int, float)): return None
    if isinstance(value, float) and not math.isfinite(value): return None
    return value if value >= 0 else None


def tool_observations(names: list[str], source: str) -> list[dict[str, Any]]:
    """One derived event per observed tool call, in the audit's vocabulary."""
    return [{"source": source, "type": "tool_observation", "declared_tool": name,
             "tool": TOOL_WORDS.get(name, name)} for name in names]


def numbered_resource(result: Any, fields: tuple[tuple[str, str], ...]) -> dict[str, Any]:
    """Provider-reported numbers, each present only if the provider sent it."""
    out: dict[str, Any] = {}
    for key, field in fields:
        value = nonnegative(result.get(field)) if isinstance(result, dict) else None
        if value is not None: out[key] = value
    return out


def merge_violations(audited: list[str], extra: list[str]) -> list[str]:
    return audited + [name for name in extra if name not in audited]


def probe_availability(executable: str, missing_class: str, request,
                       identities: dict[str, str], label: str) -> AvailabilityResult:
    """Present, a real binary, and running the task this attempt claims."""
    refusal = validate_executable_path(executable) if executable else ""
    identity, evidence = _identity(request, identities)
    failure = identity or ("" if executable else missing_class) or ("shim_or_missing_binary" if refusal else "")
    detail = identity or (missing_class if not executable else refusal) or f"{label} CLI present"
    return AvailabilityResult(not failure, failure, _clean(detail),
                              {"process_present": bool(executable), "provider_called": False,
                               "binary_check": _clean(refusal or "native_executable"), **evidence})


def terminal_state(process, malformed: bool, rejection, final_invalid: bool,
                   result: Any) -> tuple[str, str, str]:
    """The one execution verdict, in the order the failures shadow each other.

    A timeout hides everything downstream of it, malformed output hides a
    rejection that could not be parsed out of it, and a provider-reported
    error hides a nonzero exit that only restates it.
    """
    if process.timed_out: return "timeout", "timeout", process.stderr
    if malformed or process.malformed_output:
        return "malformed", "malformed_jsonl", "provider output was not bounded UTF-8 JSONL"
    if rejection: return "internal_error", rejection[0], rejection[1]
    if final_invalid:
        return "malformed", "malformed_jsonl", "result event missing or carried no final text"
    if isinstance(result, dict) and (result.get("is_error") is True or result.get("subtype") != "success"):
        return "internal_error", "provider_reported_error", str(result.get("subtype", ""))
    if process.returncode: return "internal_error", "process_nonzero", process.stderr
    return "returned", "", ""

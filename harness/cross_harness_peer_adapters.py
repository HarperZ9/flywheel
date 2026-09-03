"""Peer harness adapters: Claude Code and Cursor, captured the way codex is.

Both peers ship a print mode that emits bounded JSONL, so one capture path
serves all three: run the CLI inside the attempt workspace, parse the stream,
take the final text from the provider's own terminal event, and record what
the provider reported about itself. Nothing here scores a peer, and no field
a peer did not emit is filled in.

Two honest differences from the codex path are recorded rather than papered
over. Claude Code reports a token-usage block and a cost figure on its result
event, so those cells carry the provider's own numbers. Cursor reports
neither, so its usage cell stays empty and its cost null reason stands.

Tool names are normalized into the vocabulary ``_audit`` already classifies,
because neither peer names tools the way the audit's word rules expect:
Claude Code calls its shell tool "Bash", and Cursor puts the tool name in a
dict KEY, which the audit walk never reads because it visits values only. The
normalization is appended to the retained transcript, so a receipt shows
exactly what was classified rather than hiding the mapping in code.

The shared readers for the print-mode stream live in cross_harness_peer_stream.
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Any, Callable

from .cross_harness_adapters import (MalformedProviderOutput, _audit, _clean, _enforcement, _freeze_identities,
                                     _parse_jsonl, _run_process)
from .cross_harness_cli_identity import cli_identity_fields, codex_cli_version
from .cross_harness_peer_stream import (init_event, merge_violations, numbered_resource,
                                        probe_availability, resolve_binary, result_event,
                                        string_field, terminal_state, terminal_text,
                                        tool_observations)
from .cross_harness_provider_error import inspect_provider_events
from .cross_harness_types import AdapterResult
from .cross_harness_usage import attempt_usage

CLAUDE_ALLOWED_TOOLS = frozenset({"Read", "Grep", "Glob"})
_CONTROLS = {"type": "controls", "randomness": "unsupported",
             "max_output_control": None, "max_output_control_state": "unsupported"}


def _resolve_claude() -> str:
    return resolve_binary(("claude.exe", "claude") if os.name == "nt" else ("claude",))


def _resolve_cursor() -> str:
    return resolve_binary(("cursor-agent.exe", "cursor-agent") if os.name == "nt" else ("cursor-agent",))


def _claude_argv(executable: str, model: str, workspace: Path) -> list[str]:
    """Print mode, read-only tools, no inherited operator configuration.

    --restricted is the closest analogue to codex --sandbox read-only: it drops
    shell, REPL, and fetch tools unless --tools names them, confines file tools
    to the working directory, and refuses a bypass permission mode. --safe-mode
    is the analogue to --ignore-user-config: no CLAUDE.md, skills, plugins,
    hooks, MCP servers, or custom commands. --bare would also isolate config but
    forces API-key-only authentication, a different account than the operator
    runs, so it is not used here.
    """
    return [executable, "-p", "--output-format", "stream-json", "--verbose", "--model", model,
            "--restricted", "--safe-mode", "--strict-mcp-config", "--no-session-persistence",
            "--add-dir", str(workspace), "--tools", ",".join(sorted(CLAUDE_ALLOWED_TOOLS))]


def _cursor_argv(executable: str, model: str, workspace: Path, prompt: str) -> list[str]:
    """Print mode in the attempt workspace, sandboxed, ask mode, no writes.

    The prompt is a positional argument rather than stdin, a real difference
    from the other two harnesses that is declared as such in the enforcement
    description. A model reference of "default" sends no --model flag at all,
    so the account default runs and nothing fabricates a model name that was
    never verified against a local CLI.
    """
    argv = [executable, "agent", "-p", "--output-format", "stream-json"]
    if model and model != "default": argv += ["--model", model]
    return argv + ["--workspace", str(workspace), "--sandbox", "enabled", "--mode", "ask", prompt]


def _claude_tool_names(events: list[dict[str, Any]]) -> list[str]:
    names = []
    for event in events:
        if event.get("type") != "assistant": continue
        message = event.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        for block in content if isinstance(content, list) else []:
            if isinstance(block, dict) and block.get("type") == "tool_use" and isinstance(block.get("name"), str):
                names.append(block["name"])
    return names


def _cursor_tool_names(events: list[dict[str, Any]]) -> list[str]:
    """Cursor puts the tool name in a dict key: {"readToolCall": {...}}."""
    names = []
    for event in events:
        call = event.get("tool_call")
        if event.get("type") == "tool_call" and isinstance(call, dict):
            names += [str(key) for key in call]
    return names


def _claude_boundary(events: list[dict[str, Any]]) -> list[str]:
    """Check the declared boundary against the peer's own report of it.

    The init event states the tools, MCP servers, and permission mode actually
    in force for the run. Comparing our declaration to that report is the one
    cross-check available without trusting our own command line, and a
    disagreement is recorded as a policy violation rather than as a note.
    """
    init = init_event(events)
    if init is None: return ["boundary_report_absent"]
    out = []
    tools = init.get("tools")
    if not isinstance(tools, list): out.append("boundary_report_malformed")
    elif any(str(name) not in CLAUDE_ALLOWED_TOOLS for name in tools): out.append("declared_tool_boundary_exceeded")
    servers = init.get("mcp_servers")
    if not isinstance(servers, list) or servers: out.append("mcp_not_allowed")
    if string_field(init, "permissionMode") not in {"default", "restricted", ""}:
        out.append("permission_boundary_unexpected")
    return out


class DirectClaudeCodeAdapter:
    """Claude Code in print mode, restricted tools, no inherited configuration."""
    role, adapter_id = "claude_code", "claude_code_cli_json/v1"
    _SOURCE = "claude_code_direct"

    def __init__(self, *, runner: Callable = _run_process, executable_resolver: Callable = _resolve_claude,
                 task_identity_by_id: "dict[str, dict[str, Any]] | None" = None,
                 version_probe: Callable = codex_cli_version):
        self.runner, self.executable_resolver = runner, executable_resolver
        self.task_identities = _freeze_identities(task_identity_by_id)
        self.cli_version = version_probe(executable_resolver())

    def enforcement(self, request):
        return _enforcement({"boundary": "claude_code_print", "sandbox": "restricted", "ephemeral": True,
                             "ignore_user_config": True, "shell": False, "prompt_transport": "stdin",
                             "declared_tools": sorted(CLAUDE_ALLOWED_TOOLS), "mcp": "strict_empty",
                             "session_persistence": False, "randomness_control": "unsupported",
                             "max_output_control": None, "max_output_control_state": "unsupported"})

    def availability(self, request):
        return probe_availability(self.executable_resolver(), "claude_code_cli_missing",
                                  request, self.task_identities, "claude code")

    def execute(self, request):
        executable = self.executable_resolver()
        process = self.runner(_claude_argv(executable, request.requested_model_reference, request.workspace_root),
                              cwd=request.workspace_root, stdin_text=request.prompt,
                              timeout_seconds=request.timeout_seconds)
        events, malformed = _parse_jsonl(process.stdout, self._SOURCE)
        rejection, terminal_malformed = inspect_provider_events(events)
        malformed |= terminal_malformed
        result = result_event(events)
        try: output_text = "" if rejection or terminal_malformed else terminal_text(result)
        except MalformedProviderOutput: output_text, final_invalid = "", True
        else: final_invalid = False
        # The model the provider says answered, preferred over the model the
        # session opened with, because a fallback between them is exactly what
        # a requested reference cannot tell us.
        observed = next((string_field(event.get("message"), "model") for event in reversed(events)
                         if event.get("type") == "assistant" and string_field(event.get("message"), "model")),
                        string_field(init_event(events), "model"))
        boundary = _claude_boundary(events)
        events += tool_observations(_claude_tool_names(events), self._SOURCE)
        events.append({"source": self._SOURCE, **_CONTROLS})
        block = result.get("usage") if isinstance(result, dict) else None
        usage = _clean(block, True) if isinstance(block, dict) else None
        if usage is not None:
            # The transcript is the authority for the usage cell, so the block
            # is retained verbatim on its own derived event and the cell is
            # recomputed from it. Nested fields leave a field-wise sum
            # undefined, and the aggregate refuses itself for that named
            # reason rather than being filled from a subset of the block.
            events.append({"source": "claude_code_inner", "inner_call": 1, "type": "usage.observed",
                           "usage": usage})
        capabilities, violations = _audit(events)
        state, failure, detail = terminal_state(process, malformed, rejection, final_invalid, result)
        resource = {"inner_call_count": 1, **cli_identity_fields(self.cli_version, executable),
                    **numbered_resource(result, (("provider_reported_cost_usd", "total_cost_usd"),
                                                 ("duration_ms", "duration_ms"),
                                                 ("provider_api_duration_ms", "duration_api_ms"),
                                                 ("provider_turns", "num_turns")))}
        return AdapterResult(state, output_text if state == "returned" else "", events, process.elapsed_ms,
                             observed, "unsupported", failure, _clean(detail), resource,
                             attempt_usage([usage]) if usage is not None else {},
                             capabilities, merge_violations(violations, boundary),
                             "structured_provider_event" if observed else "unknown")


class DirectCursorAdapter:
    """cursor-agent in print mode, sandbox on, ask mode, no writes.

    Cursor reports no token counts and no cost in either output format, so the
    usage cell stays empty and the cost null reason stands. That is a real
    observed difference between the peers rather than an instrument gap on our
    side, and it is left visible instead of estimated.
    """
    role, adapter_id = "cursor", "cursor_agent_cli_json/v1"
    _SOURCE = "cursor_direct"

    def __init__(self, *, runner: Callable = _run_process, executable_resolver: Callable = _resolve_cursor,
                 task_identity_by_id: "dict[str, dict[str, Any]] | None" = None,
                 version_probe: Callable = codex_cli_version):
        self.runner, self.executable_resolver = runner, executable_resolver
        self.task_identities = _freeze_identities(task_identity_by_id)
        self.cli_version = version_probe(executable_resolver())

    def enforcement(self, request):
        return _enforcement({"boundary": "cursor_agent_print", "sandbox": "enabled", "ephemeral": False,
                             "ignore_user_config": False, "shell": False, "prompt_transport": "argv",
                             "mode": "ask", "randomness_control": "unsupported",
                             "max_output_control": None, "max_output_control_state": "unsupported"})

    def availability(self, request):
        return probe_availability(self.executable_resolver(), "cursor_cli_missing",
                                  request, self.task_identities, "cursor")

    def execute(self, request):
        executable = self.executable_resolver()
        process = self.runner(_cursor_argv(executable, request.requested_model_reference,
                                           request.workspace_root, request.prompt),
                              cwd=request.workspace_root, stdin_text="",
                              timeout_seconds=request.timeout_seconds)
        events, malformed = _parse_jsonl(process.stdout, self._SOURCE)
        rejection, terminal_malformed = inspect_provider_events(events)
        malformed |= terminal_malformed
        result = result_event(events)
        try: output_text = "" if rejection or terminal_malformed else terminal_text(result)
        except MalformedProviderOutput: output_text, final_invalid = "", True
        else: final_invalid = False
        observed = string_field(init_event(events), "model")
        events += tool_observations(_cursor_tool_names(events), self._SOURCE)
        events.append({"source": self._SOURCE, **_CONTROLS})
        capabilities, violations = _audit(events)
        state, failure, detail = terminal_state(process, malformed, rejection, final_invalid, result)
        resource = {"inner_call_count": 1, **cli_identity_fields(self.cli_version, executable),
                    **numbered_resource(result, (("duration_ms", "duration_ms"),
                                                 ("provider_api_duration_ms", "duration_api_ms")))}
        return AdapterResult(state, output_text if state == "returned" else "", events, process.elapsed_ms,
                             observed, "unsupported", failure, _clean(detail), resource, {},
                             capabilities, violations,
                             "structured_provider_event" if observed else "unknown")

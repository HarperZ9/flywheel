"""mcp_schema.py -- the tool list relay's MCP servers advertise.

Kept apart from local_mcp so the transport module stays within the size gate.
The run and start descriptions carry the grant model and the shell's
path-confinement limit, because an auto-consuming client reads them as the
contract.
"""
from __future__ import annotations

_ONLINE = {"online": {"type": "boolean", "description": "include codex/claude/gemini/deepseek; the codex and claude CLI tiers start an agent with its own shell, so they need the exec grant"}}
_RUN_ID = {"type": "object", "required": ["run_id"], "properties": {"run_id": {"type": "string"}}}
_RUN_OPTIONS = {
    "backend": {"type": "string", "description": "preferred backend name, or auto"},
    "model": {"type": "string", "description": "model hint passed to model-aware backends"},
    "max_tokens": {"type": "integer", "description": "per-turn generation token cap"},
    "check": {"type": "string", "description": "acceptance command run once through a shell at the end; needs the exec grant"},
    "test_cmd": {"type": "string", "description": "test command run through the gated run tool when no tool calls run; needs the exec grant"},
    "compact_budget": {"type": "integer", "description": "optional prompt compaction budget"},
}
_RUN_ARGS = {"type": "object", "required": ["goal"],
             "properties": {"goal": {"type": "string"},
                            "root": {"type": "string", "description": "this run's root; must resolve inside the root the server was launched with (a relative path resolves under it)"},
                            "allow_write": {"type": "boolean", "description": "ask for write on this run. Narrow only: omitted or false means off, and true cannot grant what the server was not started with; false also turns exec off"},
                            "allow_exec": {"type": "boolean", "description": "ask for a shell on this run, which also asks for write. Narrow only: omitted or false means off, and true cannot grant what the server was not started with"},
                            "max_steps": {"type": "integer"}, **_RUN_OPTIONS, **_ONLINE}}

_GRANT_NOTE = (
    "Write and exec come from how the server was started (--allow-write / --allow-exec, or "
    "RELAY_ALLOW_WRITE / RELAY_ALLOW_EXEC); both are off by default. A run asks for them with "
    "allow_write / allow_exec: an omitted argument asks for nothing, and the arguments can only "
    "narrow the launch grants, never widen them. allow_exec=true also asks for write, and "
    "allow_write=false turns exec off. check, test_cmd and the online codex/claude CLI tiers "
    "reach a shell, so they need exec. root must resolve inside the root the server was "
    "launched with (--root or RELAY_MCP_ROOT). File tools (read/list/write) are confined to "
    "root, never read the server's env file, and never write it, the run and session stores, or "
    ".git. The shell is NOT path-confined: run, test_cmd and check start in root and can reach "
    "any path the server's user can. A written file can also run later as code, for example "
    "a build script.")

TOOLS = [
    {"name": "local_agent_health",
     "description": "Report which model tiers are live (local serve/ollama, plus online providers when online=true).",
     "inputSchema": {"type": "object", "properties": dict(_ONLINE)}},
    {"name": "local_agent_chat",
     "description": "One-shot completion from the first healthy tier, with a per-turn receipt.",
     "inputSchema": {"type": "object", "required": ["prompt"],
                     "properties": {"prompt": {"type": "string"},
                                    "backend": {"type": "string"}, **_ONLINE}}},
    {"name": "local_agent_run",
     "description": "Run a gated agentic task and return the final answer and a verifiable ledger checkpoint. " + _GRANT_NOTE + " BLOCKS until done; from a phone or a flaky link, prefer local_agent_start.",
     "inputSchema": _RUN_ARGS},
    {"name": "local_agent_start",
     "description": "Start a gated agentic task in the BACKGROUND and return a run_id at once (does not block). " + _GRANT_NOTE + " Poll local_agent_status for live progress, then local_agent_result for the verified final answer. With RELAY_RUN_ROOT, witnessed progress checkpoints survive a restart as interrupted partial runs. Use this from a phone or over a flaky network, where a blocking run would drop.",
     "inputSchema": _RUN_ARGS},
    {"name": "local_agent_status",
     "description": "Progress of a background run: state (running/done/error/interrupted), the step count so far, and the latest witnessed ledger entries.",
     "inputSchema": _RUN_ID},
    {"name": "local_agent_result",
     "description": "The verified final answer and ledger checkpoint of a background run once it is done; reports 'running' until then.",
     "inputSchema": _RUN_ID},
    {"name": "local_agent_runs",
     "description": "List recent background runs (newest first) with state, timing, and step count, so a phone that lost a run_id after a restart can find it again. Persisted runs (RELAY_RUN_ROOT) survive a restart; a run cut off mid-flight lists as 'interrupted'.",
     "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 0}}}},
    {"name": "local_agent_sessions",
     "description": "List saved relay sessions (witnessed ledgers under RELAY_SESSION_DIR, or a per-user folder when it is unset) so a session started on the PC can be reopened from another device; each is re-verified on load, and a file that will not parse is counted in skipped. Pass session_id, a bare name, to get that session's transcript.",
     "inputSchema": {"type": "object", "properties": {"session_id": {
         "type": "string", "pattern": "^[A-Za-z0-9._-]{1,128}$",
         "description": "A saved session's name: letters, digits, '.', '_' or '-', no path."}}}},
    {"name": "relay.status",
     "description": "Liveness and identity of the relay MCP server (name, version, protocol). Network-free, for a fast health probe.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "relay.doctor",
     "description": "Readiness diagnostic: identity plus the local model tiers configured (serve, ollama) and the tools exposed. Network-free; use local_agent_health to actually ping tiers.",
     "inputSchema": {"type": "object", "properties": {}}},
]


def _hints(title, *, read_only=True, destructive=False, idempotent=True, open_world=False):
    return {"title": title, "readOnlyHint": read_only, "destructiveHint": destructive,
            "idempotentHint": idempotent, "openWorldHint": open_world}


# MCP tool annotations. A hint describes the tool to the client and grants
# nothing; launch grants still decide whether a run may write or execute.
# Runs state the worst case a granted run can reach: changed files and a model
# endpoint the user configured.
_RUN = _hints("Run a gated agent task", read_only=False, destructive=True,
              idempotent=False, open_world=True)
TOOL_ANNOTATIONS = {
    "local_agent_health": _hints("Check model tiers", idempotent=False, open_world=True),
    "local_agent_chat": _hints("Ask a configured model", idempotent=False, open_world=True),
    "local_agent_run": _RUN,
    "local_agent_start": {**_RUN, "title": "Start a gated agent task"},
    "local_agent_status": _hints("Background run progress"),
    "local_agent_result": _hints("Background run result"),
    "local_agent_runs": _hints("List background runs"),
    "local_agent_sessions": _hints("List saved sessions"),
    "relay.status": _hints("Relay status"),
    "relay.doctor": _hints("Relay readiness check"),
}
for _tool in TOOLS:
    _tool["title"] = TOOL_ANNOTATIONS[_tool["name"]]["title"]
    _tool["annotations"] = dict(TOOL_ANNOTATIONS[_tool["name"]])

"""coverage.py -- which paths the monitor sees before execution, and the
liveness join that catches a disabled hook.

Every path a tool call can take (E1 to E14, from the ground-truth map) has a
state: PRE (assessed before it runs), POST (seen only after, as native CLI
sessions are today) or NONE (not seen). A call on a POST or NONE path is never
written as ALLOW; it is UNVERIFIABLE. The liveness join checks that every post
event has a matching pre record: a post with no pre record is DRIFT, which is
how a skipped or disabled hook shows up.
"""
from __future__ import annotations

PRE, POST, NONE = "PRE", "POST", "NONE"

REGISTRY = {
    "E1": (PRE, "Local agent loop (text protocol)"),
    "E2": (PRE, "Gateway agent.run, text protocol"),
    "E3": (PRE, "Gateway agent.run, provider-native tools"),
    "E4": (PRE, "local-model lane over MCP"),
    "E5": (PRE, "Local agent CLI and router adapters"),
    "E6": (PRE, "MCP tools inside an agent run"),
    "E7": (NONE, "Lane tool calls and Plugins (phase 3)"),
    "E8": (NONE, "Delegated ACP agents (phase 3)"),
    "E9": (NONE, "DAP reverse requests (phase 3)"),
    "E10": (POST, "Native CLI sessions the gateway launches"),
    "E11": (PRE, "The operator's own Claude Code and Codex sessions (hook)"),
    "E12": (NONE, "relay forked executor (separate repo)"),
    "E13": (NONE, "accountable-surface actuations (separate repo)"),
    "E14": (NONE, "Oracle loop (task-authored command)"),
}


def state_for(path_id: str) -> str:
    return REGISTRY.get(path_id, (NONE, "unknown"))[0]


def rows() -> list:
    return [{"path_id": pid, "state": st, "description": desc}
            for pid, (st, desc) in REGISTRY.items()]


def coverage_for(path_id: str, base) -> str:
    """A PRE path keeps the base coverage; POST and NONE are always UNVERIFIABLE."""
    from .contract import UNVERIFIABLE
    return base if state_for(path_id) == PRE else UNVERIFIABLE


def liveness_join(records: list) -> dict:
    """A post event whose tool_use_id has no pre record is DRIFT."""
    from .records import HOLD_SCHEMA, ALLOW_SCHEMA, POST_SCHEMA, REDEEM_SCHEMA
    pre = {r.get("tool_use_id") for r in records
           if r.get("schema") in (HOLD_SCHEMA, ALLOW_SCHEMA, REDEEM_SCHEMA) and r.get("tool_use_id")}
    orphans = sorted({r.get("tool_use_id") for r in records
                      if r.get("schema") == POST_SCHEMA and r.get("tool_use_id") not in pre
                      and r.get("tool_use_id")})
    return {"verdict": "DRIFT" if orphans else "MATCH", "orphans": orphans}

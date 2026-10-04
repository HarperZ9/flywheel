"""coverage.py -- which paths the monitor sees before execution, and the
liveness join that catches a disabled hook.

Every path a tool call can take (E1 to E14, from the ground-truth map) has a
domain (inside or outside the agent's reach) and a state: PRE (assessed before it runs), POST (seen only after, as native CLI
sessions are today) or NONE (not seen). A call on a POST or NONE path is never
written as ALLOW; it is UNVERIFIABLE. The liveness join checks that every post
event has a matching pre record: a post with no pre record is DRIFT, which is
how a skipped or disabled hook shows up.
"""
from __future__ import annotations

PRE, POST, NONE = "PRE", "POST", "NONE"
INSIDE, OUTSIDE = "inside", "outside"

# path_id: (state, domain, boundary, description). Domain says where the
# component that sees the call runs relative to the agent: "inside" means in
# the agent's process tree or under the agent's OS user with no boundary
# between them, so an agent with an unrestricted shell can reach it; "outside"
# means a boundary the agent cannot write across. An inside ALLOW is weaker
# evidence than an outside one, and the verifier reports the split.
REGISTRY = {
    "E1": (PRE, INSIDE, "agent loop process", "Local agent loop (text protocol)"),
    "E2": (PRE, INSIDE, "gateway process, same user", "Gateway agent.run, text protocol"),
    "E3": (PRE, INSIDE, "gateway process, same user", "Gateway agent.run, provider-native tools"),
    "E4": (PRE, INSIDE, "lane process, same user", "local-model lane over MCP"),
    "E5": (PRE, INSIDE, "agent loop process", "Local agent CLI and router adapters"),
    "E6": (PRE, INSIDE, "agent loop process", "MCP tools inside an agent run"),
    "E7": (NONE, INSIDE, "not seen", "Lane tool calls and Plugins (phase 3)"),
    "E8": (NONE, INSIDE, "not seen", "Delegated ACP agents (phase 3)"),
    "E9": (NONE, INSIDE, "not seen", "DAP reverse requests (phase 3)"),
    "E10": (POST, INSIDE, "after the fact", "Native CLI sessions the gateway launches"),
    "E11": (PRE, INSIDE, "hook child of the agent harness",
            "The operator's own Claude Code and Codex sessions (hook)"),
    "E12": (NONE, INSIDE, "not seen", "relay forked executor (separate repo)"),
    "E13": (NONE, INSIDE, "not seen", "accountable-surface actuations (separate repo)"),
    "E14": (NONE, INSIDE, "not seen", "Oracle loop (task-authored command)"),
}

# Witnesses see calls without being on the call path, so they cannot hold a
# call. They detect a skipped hook or a rewritten store after the fact.
WITNESSES = {
    "W1": (OUTSIDE, "separate owner process, same OS user unless sandboxed",
           "Transcript witness: harness transcripts joined against pre records"),
    "W2": (OUTSIDE, "OpenShell gateway, outside the sandbox boundary",
           "OpenShell OCSF import: network and process events as sealed records"),
    "W3": (OUTSIDE, "owner witness directory; outside only when the agent cannot write it",
           "Chain-head export: store heads copied out at every stop and every N records"),
    "W4": (OUTSIDE, "separate OS identity when FLYWHEEL_SIGNER is set; inside, and "
           "labeled same-identity on every record, when the signer shares the agent's",
           "Record signer: an Ed25519 attestation on every record, refused for any "
           "sequence number already signed, and a signed head for truncation"),
}


def state_for(path_id: str) -> str:
    return REGISTRY.get(path_id, (NONE, INSIDE, "", "unknown"))[0]


def domain_for(path_id: str) -> str:
    if path_id in WITNESSES:
        return WITNESSES[path_id][0]
    return REGISTRY.get(path_id, (NONE, INSIDE, "", "unknown"))[1]


def rows() -> list:
    out = [{"path_id": pid, "kind": "path", "state": st, "domain": dom, "boundary": bnd,
            "description": desc} for pid, (st, dom, bnd, desc) in REGISTRY.items()]
    out += [{"path_id": wid, "kind": "witness", "state": "WITNESS", "domain": dom,
             "boundary": bnd, "description": desc} for wid, (dom, bnd, desc) in WITNESSES.items()]
    return out


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

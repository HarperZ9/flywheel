"""policy.py — layered authorization gate before every handler.

Server-level (default egress envelope) -> tool-level (static capability shape)
-> call-level (args/context decisive). First non-ALLOW layer wins. A blocked
call is a completed POLICY decision, not a failed execution: the handler never
runs, so no verification verdict applies.

Trace hygiene: PolicyResult carries args_hash + evidence_ref, never raw args,
paths, env, or secrets. The model sees a compact reason + "no side effect" —
debuggable without leaking private FS/network/credential detail.

Composes with behavior-transform.io: policy decides whether the call may run;
behavior-transform receipts what actually ran when it does. Admission (here) is
orthogonal to verification (oracle/witness) — the ledger contract's "separate
admission decisions from verification verdicts" made concrete.
"""
from __future__ import annotations
import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol


class Decision(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"
    ESCALATE = "escalate"
    TRANSFORM = "transform"


@dataclass
class PolicyResult:
    decision: Decision
    boundary: str          # server | tool | call
    policy_id: str
    reason_code: str
    args_hash: str
    evidence_ref: str | None = None
    transformed_args: dict | None = None
    note: str = ""         # compact model-facing reason

    @property
    def allowed(self) -> bool:
        return self.decision == Decision.ALLOW

    def to_trace(self) -> dict:
        return {
            "decision": self.decision.value, "boundary": self.boundary,
            "policy_id": self.policy_id, "reason_code": self.reason_code,
            "args_hash": self.args_hash, "evidence_ref": self.evidence_ref,
        }


def args_hash(args: dict) -> str:
    return hashlib.sha256(
        json.dumps(args, sort_keys=True, default=str).encode()).hexdigest()[:16]


class PolicyLayer(Protocol):
    boundary: str

    def decide(self, tool: str, args: dict, ctx: dict) -> PolicyResult | None:
        """Return a non-ALLOW result to decide, or None to defer to next layer."""
        ...


def gate(layers: list[PolicyLayer], tool: str, args: dict,
        ctx: dict | None = None) -> PolicyResult:
    ctx = ctx or {}
    ah = args_hash(args)
    for layer in layers:
        r = layer.decide(tool, args, ctx)
        if r is not None and r.decision != Decision.ALLOW:
            return r
    return PolicyResult(Decision.ALLOW, "call", "default-allow",
                        "no_rule_matched", ah)


DENY_SHELL_TOKENS = [
    r"\brm\s+-rf\b", r"\bcurl\b", r"\bwget\b", r"\bnc\b",
    r"\bmkfs\b", r"\bdd\b\s+if=", r"\bshutdown\b", r"\biex\b",
]


class CallShellPolicy:
    """Call-level gate for shell-executing tools (e.g. the oracle).

    Blocks commands containing destructive/network tokens, and commands whose
    workdir escapes an allowed root set. Not a full sandbox — that is
    behavior-transform's job. This is the admission decision before the run.
    """
    boundary = "call"

    def __init__(self, allowed_roots: list[str] | None = None,
                 deny_patterns: list[str] | None = None,
                 policy_id: str = "call-shell-v1"):
        self.allowed_roots = [p.lower().replace("\\", "/").rstrip("/")
                              for p in (allowed_roots or [])]
        self.deny = [re.compile(p, re.I) for p in (deny_patterns or DENY_SHELL_TOKENS)]
        self.policy_id = policy_id

    def decide(self, tool: str, args: dict, ctx: dict) -> PolicyResult | None:
        if tool != "oracle.run":
            return None
        cmd = str(args.get("cmd", ""))
        ah = args_hash(args)
        for pat in self.deny:
            if pat.search(cmd):
                return PolicyResult(
                    Decision.BLOCK, "call", self.policy_id,
                    "denied_shell_token", ah,
                    note=f"command matched denied pattern; no side effect occurred")
        wd = str(args.get("workdir", "")).lower().replace("\\", "/")
        if self.allowed_roots and wd:
            if not any(wd.startswith(r) for r in self.allowed_roots):
                return PolicyResult(
                    Decision.BLOCK, "call", self.policy_id,
                    "workdir_outside_allowed_roots", ah,
                    note="workdir escapes allowed roots; no side effect occurred")
        return None


class ToolCapabilityPolicy:
    """Tool-level static capability shape: allowed tools + side-effect class."""
    boundary = "tool"

    def __init__(self, allowed_tools: list[str], policy_id: str = "tool-cap-v1"):
        self.allowed = set(allowed_tools)
        self.policy_id = policy_id

    def decide(self, tool: str, args: dict, ctx: dict) -> PolicyResult | None:
        if tool not in self.allowed:
            return PolicyResult(
                Decision.BLOCK, "tool", self.policy_id,
                "tool_not_in_capability_set", args_hash(args),
                note="tool outside declared capability shape; no side effect occurred")
        return None


def default_harness_gate(allowed_roots: list[str]) -> list[PolicyLayer]:
    return [
        ToolCapabilityPolicy(
            ["oracle.run", "proposer.generate", "boot.scan"]),
        CallShellPolicy(allowed_roots=allowed_roots),
    ]

"""contract.py -- the one shape every attach point hands the monitor.

A ProposedCall is what an agent asked to do, before it runs. A RunContext is
what the owner set for the run: the goal (owner-authored, never agent text),
the workspace, the hosts the owner allows and owns, and planted canaries. An
Assessment is the monitor's answer: ALLOW, HOLD (stop and ask the owner) or
BLOCK (stop, record, tell the owner). The monitor judges the proposed action,
its arguments and the trajectory. It never judges intent.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

ALLOW, HOLD, BLOCK = "ALLOW", "HOLD", "BLOCK"
VERDICTS = (ALLOW, HOLD, BLOCK)
MATCH, DRIFT, UNVERIFIABLE = "MATCH", "DRIFT", "UNVERIFIABLE"
_RANK = {ALLOW: 0, HOLD: 1, BLOCK: 2}

DOES_NOT_PROVE = {
    HOLD: "Matched rule or threshold; says nothing about intent.",
    BLOCK: "Matched rule or threshold; says nothing about intent.",
    ALLOW: "No rule fired and the judge, if on, scored below threshold; safety stays open.",
    UNVERIFIABLE: "The monitor could not assess this call; it was not treated as safe.",
}
REVIEW_DOES_NOT_PROVE = (
    "This shows the proposed action matched a rule or scored above a threshold. "
    "It does not show intent. The agent's task, instructions and environment "
    "explain the behavior.")

_BUILTIN_CAPABILITY = {
    "write_file": "builtin-write", "edit_file": "builtin-write", "apply_patch": "builtin-write",
    "run": "builtin-exec", "read_file": "builtin-read", "list_dir": "builtin-read",
    "grep": "builtin-read", "glob": "builtin-read", "repo_map": "builtin-read",
    # Claude Code and Codex tool names
    "Read": "builtin-read", "Glob": "builtin-read", "Grep": "builtin-read",
    "LS": "builtin-read", "Write": "builtin-write", "Edit": "builtin-write",
    "MultiEdit": "builtin-write", "NotebookEdit": "builtin-write",
    "Bash": "builtin-exec", "shell": "builtin-exec", "local_shell": "builtin-exec",
}


def worse(a: str, b: str) -> str:
    """The stricter of two verdicts. Layers combine through this only, so no
    layer can turn another layer's HOLD or BLOCK into ALLOW (demote-only)."""
    return a if _RANK[a] >= _RANK[b] else b


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8", "surrogatepass")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def classify_capability(tool: str) -> str:
    if tool.startswith("mcp__"):
        return "external-mcp"
    return _BUILTIN_CAPABILITY.get(tool, "unknown")


@dataclass(frozen=True)
class ProposedCall:
    tool: str
    args: dict
    harness: str = "flywheel"
    path_id: str = "E1"
    capability: str = ""
    tool_use_id: str = ""
    seq: int = 0

    def capability_class(self) -> str:
        return self.capability or classify_capability(self.tool)

    def args_bytes(self) -> bytes:
        return canonical_json(self.args) if self.args else b""

    def args_sha256(self) -> str:
        return sha256_hex(self.args_bytes())

    def call_sha256(self) -> str:
        """The normalized call: tool plus argument digest. Repeat-after-reject
        and grant redemption both key on this."""
        return sha256_hex(canonical_json({"tool": self.tool, "args": self.args_sha256()}))


@dataclass
class RunContext:
    run_id: str = ""
    owner_ref: str = ""
    goal: str = ""
    workspace: str = ""
    allow_hosts: tuple = ()
    owned_hosts: tuple = ()
    fetch_hosts: tuple = ()      # read-only fetches only (fetch.py), never uploads
    canaries: tuple = ()
    protected_paths: tuple = ()
    interactive: bool = False

    def goal_sha256(self) -> str:
        return sha256_hex(self.goal.encode("utf-8"))


@dataclass(frozen=True)
class Hit:
    """One reason a layer stopped a call."""
    id: str
    family: str
    action: str
    reason: str
    layer: int = 1

    def to_dict(self) -> dict:
        return {"layer": self.layer, "id": self.id, "family": self.family,
                "action": self.action, "reason": self.reason}


@dataclass
class Assessment:
    verdict: str
    reasons: list = field(default_factory=list)
    coverage: str = MATCH
    path_id: str = "E1"
    rules_digest: str = ""
    config_sha256: str = ""
    config_pin: str = "UNPINNED"
    judge: dict = field(default_factory=lambda: {"state": "off"})
    hold_id: str = ""
    record_sha256: str = ""

    def rule_hits(self) -> list:
        return [r["id"] for r in self.reasons if r.get("layer") in (0, 1, 9)]

    def trajectory_hits(self) -> list:
        return [r["id"] for r in self.reasons if r.get("layer") == 2]

    def preaction_block(self, decision: dict | None = None) -> dict:
        """The optional block the after-receipt carries, in fixed field order,
        integers and strings only (the v1 receipt contract has no floats)."""
        judge = {"state": str(self.judge.get("state", "off"))}
        for key in ("model_ref", "prompt_sha256", "input_sha256", "output_sha256", "outcome"):
            if key in self.judge:
                judge[key] = str(self.judge[key])
        for key in ("score", "threshold", "p_hold_permille"):
            if isinstance(self.judge.get(key), int):
                judge[key] = int(self.judge[key])
        return {
            "hold_record_sha256": self.record_sha256,
            "verdict": self.verdict,
            "path_id": self.path_id,
            "coverage": self.coverage,
            "rules_digest": self.rules_digest,
            "rule_hits": self.rule_hits(),
            "trajectory_hits": self.trajectory_hits(),
            "judge": judge,
            "decision": decision or {"kind": "NONE", "record_sha256": "", "grant_id": ""},
        }

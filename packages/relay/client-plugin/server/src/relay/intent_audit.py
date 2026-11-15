"""intent_audit.py -- audit a witnessed run against declared intent and scope.

Ported from the (archived) agent-audit tool and adapted to relay's hash-chained
ledger, so the capability lives in a live lane instead of a frozen repo. Three
detectors over the trajectory, all facts from the ledger like review.py:

- claimed_history: an assistant turn that claims prior work ("I previously ran the
  tests") with no earlier tool action in the ledger to back it. This catches the
  agent asserting work it never did -- the failure a witnessed ledger exists to
  expose. It needs no declaration and runs on every relay run.
- intent_drift: a tool call whose tool is outside a declared Intent. Optional; runs
  only when an Intent is supplied. (relay tools carry no abstract target class, so
  only the tool-name axis is ported; that gap is an honest null.)
- scope_violation: a tool call that breaks a declared ScopePolicy (denied tools,
  denied targets, or a max action count). Optional; runs only when a policy is set.

A surface decides what to do with the findings; this module only reports them.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

SCHEMA = "relay.intent-audit/v1"
CRITICAL = "critical"
WARN = "warn"

# reasoning that asserts earlier work; lowercased substring match.
_CLAIMED_HISTORY_MARKERS = (
    "i previously", "i already", "i have completed", "after completing",
    "given my earlier", "having run", "as i ran", "i ran the",
)


@dataclass(frozen=True)
class Intent:
    """The tools a run declared it intended to use."""
    tools: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class ScopePolicy:
    """Bounds a run's tool calls: an allow/deny set, denied targets, a call cap."""
    allowed_tools: frozenset[str] = field(default_factory=frozenset)
    denied_tools: frozenset[str] = field(default_factory=frozenset)
    denied_targets: frozenset[str] = field(default_factory=frozenset)
    max_actions: int | None = None


def _field(entry, name, default=None):
    if isinstance(entry, dict):
        return entry.get(name, default)
    return getattr(entry, name, default)


def _parse_call(content: str) -> tuple[str, dict]:
    name, _, rest = (content or "").partition(" ")
    try:
        args = json.loads(rest) if rest else {}
    except ValueError:
        args = {}
    return name, args if isinstance(args, dict) else {}


def _target(args: dict) -> str:
    return str(args.get("path") or args.get("cmd") or "")


def _finding(detector: str, severity: str, seq, summary: str, detail: dict) -> dict:
    return {"detector": detector, "severity": severity, "seq": seq,
            "summary": summary, "detail": detail}


def claimed_history(entries: list) -> list[dict]:
    """Flag an assistant turn that claims prior work before any tool has run."""
    findings: list[dict] = []
    prior_actions = 0
    for entry in entries:
        kind = _field(entry, "kind", "")
        if kind == "tool_call":
            prior_actions += 1
        elif kind == "assistant":
            text = (_field(entry, "content", "") or "").lower()
            marker = next((m for m in _CLAIMED_HISTORY_MARKERS if m in text), "")
            if marker and prior_actions == 0:
                findings.append(_finding(
                    "claimed_history", CRITICAL, _field(entry, "seq"),
                    f"reasoning claims prior work ({marker!r}) with no earlier tool action",
                    {"marker": marker, "prior_actions": prior_actions}))
    return findings


def intent_drift(entries: list, intent: "Intent | None") -> list[dict]:
    """Flag a tool call whose tool is outside the declared intent."""
    if intent is None or not intent.tools:
        return []
    findings: list[dict] = []
    for entry in entries:
        if _field(entry, "kind", "") != "tool_call":
            continue
        name, _ = _parse_call(_field(entry, "content", ""))
        if name and name not in intent.tools:
            findings.append(_finding(
                "intent_drift", WARN, _field(entry, "seq"),
                f"tool {name!r} is outside the declared intent",
                {"tool": name, "intended": sorted(intent.tools)}))
    return findings


def scope_violations(entries: list, policy: "ScopePolicy | None") -> list[dict]:
    """Flag a tool call that breaks the declared scope policy."""
    if policy is None:
        return []
    findings: list[dict] = []
    count = 0
    for entry in entries:
        if _field(entry, "kind", "") != "tool_call":
            continue
        name, args = _parse_call(_field(entry, "content", ""))
        target = _target(args)
        reasons = []
        if name in policy.denied_tools:
            reasons.append(f"tool {name!r} is denied")
        if policy.allowed_tools and name not in policy.allowed_tools:
            reasons.append(f"tool {name!r} is not in the allowed set")
        if target and target in policy.denied_targets:
            reasons.append(f"target {target!r} is denied")
        if policy.max_actions is not None and count >= policy.max_actions:
            reasons.append(f"action limit reached at {policy.max_actions}")
        count += 1
        if reasons:
            findings.append(_finding(
                "scope_violation", CRITICAL, _field(entry, "seq"),
                "; ".join(reasons), {"tool": name, "target": target}))
    return findings


def audit_intent(ledger, *, intent: "Intent | None" = None,
                 policy: "ScopePolicy | None" = None) -> dict:
    """Audit a ledger (or its entries) for claimed history, and -- when declared --
    intent drift and scope violations. Returns a findings report."""
    entries = getattr(ledger, "entries", ledger)
    findings = (claimed_history(entries)
                + intent_drift(entries, intent)
                + scope_violations(entries, policy))
    critical = sum(1 for f in findings if f["severity"] == CRITICAL)
    return {"schema": SCHEMA, "findings": findings,
            "critical": critical, "warnings": len(findings) - critical,
            "note": "facts from the witnessed ledger only"}

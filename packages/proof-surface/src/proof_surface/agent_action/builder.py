"""Assemble an agent-action proof packet from a trace + an authorization receipt.

Admission is *derived*, not asserted: each material action is run through
proof-surface's own authorization_receipt.check_action against a real,
least-privilege, expiring grant. The verdict layer is left UNVERIFIABLE
(fail-closed) for the crucible bridge to fill after judgement.

Depends only on sibling proof-surface modules -- no third-party packages, and
crucially no dependency on accountable-surface, so the packet stays
pip-installable and runnable by a third party.
"""

from __future__ import annotations

from typing import Any

from .._decision import derive_decision_summary
from ..authorization_receipt import check_action
from .importer import ActionRecord, _canonical_digest, import_trace
from .packet import PACKET_VERSION


def build_agent_action_packet(
    trace: dict[str, Any],
    authorization: dict[str, Any],
    *,
    claim: str,
    scope: str,
    packet_id: str,
    evidence_refs: dict[str, Any] | None = None,
    failure_labels: list[str] | None = None,
) -> dict[str, Any]:
    imported = import_trace(trace)
    auth_ref = authorization.get("receipt_id", "")

    packet = {
        "version": PACKET_VERSION,
        "packet_id": packet_id,
        "claim": claim,
        "scope": scope,
        "sources": [
            {
                "ref": f"trace:{trace.get('trace_id', '')}",
                "sha256": _canonical_digest(trace),
            }
        ],
        "context": {
            "service": trace.get("service", ""),
            "trace_id": trace.get("trace_id", ""),
            "tool_authority": auth_ref,
        },
        "actions": [_action_dict(a) for a in imported.actions],
        "admission": [
            _admission_dict(a, authorization, auth_ref) for a in imported.actions
        ],
        "side_effects": [_side_effect_dict(a) for a in imported.actions],
        "outputs": _outputs(imported.actions),
        "verdicts": {
            "overall": "UNVERIFIABLE",
            "per_action": [
                {"action_id": a.action_id, "status": "UNVERIFIABLE"}
                for a in imported.actions
            ],
        },
        "uncertainty": [
            f"flagged span {f.span_id}: {f.reason}" for f in imported.flagged
        ],
        "decision_summary": derive_decision_summary("UNVERIFIABLE"),
    }
    if evidence_refs is not None:
        packet["evidence_refs"] = {
            key: list(value) for key, value in evidence_refs.items()
        }
    if failure_labels is not None:
        packet["failure_labels"] = list(failure_labels)
    return packet


def _action_dict(a: ActionRecord) -> dict[str, Any]:
    return {
        "action_id": a.action_id,
        "actor": a.actor,
        "agent": a.agent,
        "model": a.model,
        "tool": a.tool,
        "action_kind": a.action_kind,
        "target": a.target,
        "cost": a.cost,
        "span_digest": a.span_digest,
    }


def _admission_dict(
    a: ActionRecord, authorization: dict[str, Any], auth_ref: str
) -> dict[str, Any]:
    denial = check_action(authorization, a.action_kind or "", a.target or "")
    if denial is None:
        return {
            "action_id": a.action_id,
            "decision": "allow",
            "reasons": [],
            "authorization_ref": auth_ref,
        }
    return {
        "action_id": a.action_id,
        "decision": "deny",
        "reasons": [_deny_reason(denial.path, a.action_kind, a.target)],
        "authorization_ref": auth_ref,
    }


# Neutral denial phrasing. The raw check_action messages say "not in
# allowed_targets/allowed_actions", and the packet's authority-language guard
# (correctly) treats "allowed" as a forbidden authority token, so the reason is
# restated faithfully without that vocabulary.
def _deny_reason(path: str, action_kind: str | None, target: str | None) -> str:
    if path.endswith("allowed_actions"):
        return f"action_kind {action_kind!r} is outside the grant scope"
    if path.endswith("allowed_targets"):
        return f"target {target!r} is outside the grant scope"
    if path.endswith("revoked"):
        return "the grant has been revoked"
    if path.endswith("granted_at"):
        return "the grant is not yet in effect"
    if path.endswith("expires_at"):
        return "the grant has expired"
    return "the action is not covered by a valid grant"


def _side_effect_dict(a: ActionRecord) -> dict[str, Any]:
    reversible = (
        a.reversible if a.reversible is not None else (a.side_effect_class == "write")
    )
    return {
        "action_id": a.action_id,
        "class": a.side_effect_class,
        "idempotency_key": a.content_sha256 or a.span_digest,
        "compensation": {"reversible": reversible, "rollback_ref": a.rollback_ref},
        "before_digest": a.before_digest,
        "after_digest": a.after_digest,
    }


def _outputs(actions: list[ActionRecord]) -> list[dict[str, Any]]:
    outputs = []
    for a in actions:
        digest = a.after_digest or a.content_sha256
        if digest and a.target:
            outputs.append({"name": a.target, "sha256": digest})
    return outputs

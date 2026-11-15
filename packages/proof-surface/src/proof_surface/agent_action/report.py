"""Reviewer-facing Markdown report for an agent-action proof packet.

The load-bearing section is Trace vs Receipt: it states plainly what a raw
observability trace shows versus what this receipt adds. Stdlib-only.
"""

from __future__ import annotations

from typing import Any

from .._boundary import render_boundary
from .._decision import render_decision_summary


def _short(digest: Any) -> str:
    if isinstance(digest, str) and digest:
        return f"`{digest[:12]}...`"
    return "_none_"


def _index(entries: Any) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if isinstance(entries, list):
        for e in entries:
            if isinstance(e, dict) and isinstance(e.get("action_id"), str):
                out.setdefault(e["action_id"], e)
    return out


_TRACE_VS_RECEIPT = """## Trace vs Receipt

| Layer | A raw trace shows | This receipt adds |
| --- | --- | --- |
| Action | tool spans -- what ran | actor, target, and a content-addressed span digest |
| Admission | (nothing) | allow / deny / needs-human, the grant it was checked against, and the reason |
| Side effect | (nothing) | class, idempotency key, compensation / rollback, before -> after digest |
| Provenance | one vendor's spans | preserved trace / eval / model / runtime refs to the incumbent systems |
| Verification | (nothing) | a re-derivable MATCH / DRIFT / UNVERIFIABLE verdict |
"""


def render_report(packet: dict[str, Any]) -> str:
    overall = (packet.get("verdicts") or {}).get("overall", "UNVERIFIABLE")
    lines = [
        f"# Agent-Action Proof Packet `{packet.get('packet_id', '')}`",
        "",
        f"**Verdict: {overall}** -- {packet.get('claim', '')}",
        "",
        f"- **Scope:** {packet.get('scope', '')}",
        f"- **Sources:** {len(packet.get('sources') or [])}"
        f" - **Actions:** {len(packet.get('actions') or [])}"
        f" - **Flagged/uncertain:** {len(packet.get('uncertainty') or [])}",
        "",
        _TRACE_VS_RECEIPT,
    ]
    lines.extend(render_decision_summary(packet.get("decision_summary")))
    lines.extend(["", "## Actions", ""])
    lines.extend(_render_actions(packet))
    lines.extend(_render_outputs(packet.get("outputs")))
    lines.extend(_render_evidence_refs(packet.get("evidence_refs")))
    lines.extend(_render_failure_labels(packet.get("failure_labels")))
    lines.extend(_render_list("Uncertainty", packet.get("uncertainty")))
    lines.append("")
    lines.append(
        "_Every verdict is re-derivable: the packet emits a crucible thesis + "
        "measurements so an independent checker recomputes MATCH/DRIFT/UNVERIFIABLE "
        "from the same evidence._"
    )
    lines.extend(render_boundary())
    return "\n".join(lines)


def _render_actions(packet: dict[str, Any]) -> list[str]:
    admission = _index(packet.get("admission"))
    side_effects = _index(packet.get("side_effects"))
    per_action = _index(
        (packet.get("verdicts") or {}).get("per_action")
        if isinstance(packet.get("verdicts"), dict)
        else None
    )
    out: list[str] = []
    actions = packet.get("actions") or []
    if not actions:
        out.append("_No material (side-effecting) actions in this run._")
        out.append("")
        return out
    for action in actions:
        if not isinstance(action, dict):
            continue
        aid = action.get("action_id")
        status = (per_action.get(aid, {}) or {}).get("status", "UNVERIFIABLE")
        out.append(
            f"### `{action.get('action_kind')}` on `{action.get('target')}` -- {status}"
        )
        out.append(
            f"- tool `{action.get('tool')}` - actor `{action.get('actor')}`"
            f" - model `{action.get('model')}`"
        )
        out.append(_render_admission(admission.get(aid, {})))
        out.append(_render_side_effect(side_effects.get(aid, {})))
        out.append("")
    return out


def _render_admission(entry: dict[str, Any]) -> str:
    decision = str(entry.get("decision", "unknown")).upper()
    reasons = entry.get("reasons") or []
    ref = entry.get("authorization_ref", "")
    tail = f" -- {'; '.join(reasons)}" if reasons else ""
    return f"- **Admission:** {decision} (grant `{ref}`){tail}"


def _render_side_effect(entry: dict[str, Any]) -> str:
    comp = entry.get("compensation") or {}
    reversible = comp.get("reversible")
    rollback = comp.get("rollback_ref")
    comp_txt = "reversible" if reversible else "irreversible"
    if reversible and rollback:
        comp_txt += f" (rollback `{rollback}`)"
    line = (
        f"- **Side effect:** {entry.get('class')}; "
        f"idempotency {_short(entry.get('idempotency_key'))}; {comp_txt}; "
        f"{_short(entry.get('before_digest'))} -> {_short(entry.get('after_digest'))}"
    )
    lease = entry.get("compute_lease")
    if isinstance(lease, dict):
        line += (
            f"; compute-lease `{lease.get('queue_id')}` "
            f"(budget `{lease.get('budget_ref')}`, {lease.get('terminal_status')})"
        )
    return line


def _render_outputs(outputs: Any) -> list[str]:
    out = ["## Outputs", ""]
    if isinstance(outputs, list) and outputs:
        for o in outputs:
            if isinstance(o, dict):
                out.append(f"- `{o.get('name')}` -- {_short(o.get('sha256'))}")
    else:
        out.append("_none_")
    out.append("")
    return out


def _render_evidence_refs(evidence_refs: Any) -> list[str]:
    if not isinstance(evidence_refs, dict) or not evidence_refs:
        return []
    out = ["## Evidence references", ""]
    for bucket in ("trace_refs", "eval_refs", "model_refs", "runtime_refs"):
        entries = evidence_refs.get(bucket)
        if not isinstance(entries, list) or not entries:
            continue
        refs = ", ".join(
            f"`{e.get('ref')}`" for e in entries if isinstance(e, dict) and e.get("ref")
        )
        out.append(f"- **{bucket}:** {refs}")
    out.append("")
    return out


def _render_failure_labels(labels: Any) -> list[str]:
    if not isinstance(labels, list) or not labels:
        return []
    codes = ", ".join(f"`{code}`" for code in labels)
    return ["## Typed failures", "", f"- {codes}", ""]


def _render_list(title: str, items: Any) -> list[str]:
    out = [f"## {title}", ""]
    if isinstance(items, list) and items:
        out.extend(f"- {item}" for item in items)
    else:
        out.append("_none_")
    return out

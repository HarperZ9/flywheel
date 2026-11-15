"""Trace importer: normalized span tree -> agent-action records.

Reads a normalized, OpenTelemetry-shaped span tree and turns *material*
(side-effecting) spans into ActionRecords. Read-only / internal spans become
context. A span that carries a side-effect marker but no action target is
*flagged*, never silently dropped (fail-closed).

Zero third-party dependencies -- stdlib only, like the rest of proof-surface.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

# Side-effect classes that make a span a *material* action (vs. read-only).
MATERIAL_CLASSES = {"write", "external", "irreversible"}


@dataclass(frozen=True)
class ActionRecord:
    """One material, side-effecting action lifted out of a trace span."""

    action_id: str
    actor: str | None
    agent: str | None
    model: str | None
    tool: str | None
    action_kind: str | None
    target: str | None
    side_effect_class: str | None
    cost: dict[str, Any]
    span_digest: str
    sources: list[dict[str, str]] = field(default_factory=list)
    # Side-effect evidence lifted from the span (an accountable actuation run
    # produces these; an external call may leave before/after None).
    content_sha256: str | None = None
    before_digest: str | None = None
    after_digest: str | None = None
    reversible: bool | None = None
    rollback_ref: str | None = None


@dataclass(frozen=True)
class ContextSpan:
    """A non-material span retained as context (never dropped)."""

    span_id: str
    name: str
    side_effect_class: str | None


@dataclass(frozen=True)
class Flagged:
    """A span that looks side-effecting but is missing a required field."""

    span_id: str
    reason: str


@dataclass(frozen=True)
class TraceImport:
    actions: list[ActionRecord]
    context_spans: list[ContextSpan]
    flagged: list[Flagged]


def _canonical_digest(obj: Any) -> str:
    """SHA-256 over canonical JSON (sorted keys, compact, ASCII)."""
    canonical = json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _cost(attributes: dict[str, Any]) -> dict[str, Any]:
    cost: dict[str, Any] = {}
    if "cost.tokens" in attributes:
        cost["tokens"] = attributes["cost.tokens"]
    if "cost.wall_ms" in attributes:
        cost["wall_ms"] = attributes["cost.wall_ms"]
    return cost


def _action_from_span(span: dict[str, Any], attributes: dict[str, Any]) -> ActionRecord:
    return ActionRecord(
        action_id=span.get("span_id", ""),
        actor=attributes.get("actor.id"),
        agent=attributes.get("agent.id"),
        model=attributes.get("model.id"),
        tool=attributes.get("tool.name"),
        action_kind=attributes.get("action.kind"),
        target=attributes.get("action.target"),
        side_effect_class=attributes.get("side_effect.class"),
        cost=_cost(attributes),
        span_digest=_canonical_digest(span),
        content_sha256=attributes.get("content.sha256"),
        before_digest=attributes.get("before.sha256"),
        after_digest=attributes.get("after.sha256"),
        reversible=attributes.get("reversible"),
        rollback_ref=attributes.get("rollback.ref"),
    )


def import_trace(trace: dict[str, Any]) -> TraceImport:
    """Split a normalized span tree into material actions, context, and flags."""
    actions: list[ActionRecord] = []
    context_spans: list[ContextSpan] = []
    flagged: list[Flagged] = []

    for span in trace.get("spans", []):
        attributes = span.get("attributes", {}) or {}
        se_class = attributes.get("side_effect.class")
        if se_class in MATERIAL_CLASSES:
            if not attributes.get("action.target"):
                flagged.append(
                    Flagged(
                        span_id=span.get("span_id", ""),
                        reason=f"{se_class!r} side-effect span missing action.target",
                    )
                )
            else:
                actions.append(_action_from_span(span, attributes))
        else:
            context_spans.append(
                ContextSpan(
                    span_id=span.get("span_id", ""),
                    name=span.get("name", ""),
                    side_effect_class=se_class,
                )
            )

    return TraceImport(actions=actions, context_spans=context_spans, flagged=flagged)

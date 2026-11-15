"""describe.py -- one printable line per record, for listings and reports.

A listing names a record by kind, id and the field a person would recognise it
by. The line is flattened to one physical line so a record body cannot forge a
second entry in a terminal listing or a truncation report.
"""
from __future__ import annotations

from canon.schema import (
    KIND_ADR_DECISION,
    KIND_ENVIRONMENT_CONSTRAINT,
    KIND_EPISODIC_MEMORY,
    KIND_PERSONALITY_BLOCK,
    KIND_RESEARCH_ARTIFACT_REF,
    KIND_SYNTHESIZED_PERSONA_L3,
    KIND_WORK_ITEM,
    KIND_WORKSPACE_FOCUS,
    Record,
)

_LABEL_FIELD = {
    KIND_PERSONALITY_BLOCK: "title",
    KIND_ADR_DECISION: "title",
    KIND_EPISODIC_MEMORY: "text",
    KIND_SYNTHESIZED_PERSONA_L3: "text",
    KIND_RESEARCH_ARTIFACT_REF: "locator",
    KIND_WORKSPACE_FOCUS: "goal",
    KIND_WORK_ITEM: "title",
    KIND_ENVIRONMENT_CONSTRAINT: "statement",
}


def flat(text: object, limit: int = 120) -> str:
    """`text` on one line, cut to `limit` characters."""
    joined = " ".join(str(text).split())
    return joined if len(joined) <= limit else joined[: limit - 3] + "..."


def label(record: Record) -> str:
    """The human name of a record: its title, statement, goal or text."""
    data = record.data if isinstance(record.data, dict) else {}
    field = _LABEL_FIELD.get(record.kind)
    value = data.get(field) if field else None
    return flat(value if value else record.id)


def summary(record: Record) -> str:
    """`kind id: label`, one line."""
    return f"{record.kind} {record.id}: {label(record)}"

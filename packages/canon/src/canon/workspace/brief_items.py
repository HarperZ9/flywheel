"""brief_items.py -- which records a resume brief shows, in what order, and how
each one reads.

A brief has four sections, in priority order: the current focus, the open work,
the recent decisions with the alternatives that were dropped, and the
constraints and quirks. Inside a section this project's records come first,
then global records, then records of a declared project, each of the latter two
labelled with where it came from. A record that belongs in no section is
excluded by rule and named with the rule, so the receipt can say why it is
absent without calling that a truncation.

Every line is flattened to one physical line and nothing is cut: a record too
long for the budget is left out whole and reported, never shortened silently.
"""
from __future__ import annotations

from dataclasses import dataclass

from canon.layering import is_current
from canon.schema import (
    KIND_ADR_DECISION,
    KIND_ENVIRONMENT_CONSTRAINT,
    KIND_PERSONALITY_BLOCK,
    KIND_WORK_ITEM,
    KIND_WORKSPACE_FOCUS,
    OPEN_WORK_STATUSES,
    Record,
)
from canon.workspace.pool import TaggedRecord

SECTION_FOCUS = "Focus"
SECTION_WORK = "Open work"
SECTION_DECISIONS = "Decisions"
SECTION_CONSTRAINTS = "Constraints and quirks"
SECTIONS = (SECTION_FOCUS, SECTION_WORK, SECTION_DECISIONS, SECTION_CONSTRAINTS)
_SECTION_OF = {
    KIND_WORKSPACE_FOCUS: SECTION_FOCUS,
    KIND_WORK_ITEM: SECTION_WORK,
    KIND_ADR_DECISION: SECTION_DECISIONS,
    KIND_ENVIRONMENT_CONSTRAINT: SECTION_CONSTRAINTS,
}
_STATUS_RANK = {"in-progress": 0, "blocked": 1, "open": 2}
NO_FILE_REASON = "instruction block: the markdown target has no instruction file"


@dataclass(frozen=True, slots=True)
class BriefItem:
    section: str
    project_id: str | None
    record: Record
    lines: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Exclusion:
    project_id: str | None
    kind: str
    id: str
    reason: str


def one_line(text: object) -> str:
    return " ".join(str(text).split())


def _origin(project_id: str | None, own: str) -> tuple[int, str]:
    if project_id == own:
        return (0, "")
    return (1, "") if project_id is None else (2, project_id)


def _tag(project_id: str | None, own: str) -> str:
    if project_id == own:
        return ""
    return " [global]" if project_id is None else f" [from {project_id}]"


def _exclusion_reason(rec: Record, has_file: bool) -> str | None:
    if not is_current(rec):
        return "not current"
    if rec.kind == KIND_PERSONALITY_BLOCK:
        return ("instruction block: rendered in the instruction region" if has_file
                else NO_FILE_REASON)
    if rec.kind not in _SECTION_OF:
        return "not a brief kind"
    if rec.kind == KIND_WORK_ITEM and rec.data.get("status") not in OPEN_WORK_STATUSES:
        return "closed work item"
    if rec.kind == KIND_ADR_DECISION and rec.data.get("status") == "superseded":
        return "superseded decision"
    return None


def _sort_key(item: TaggedRecord, own: str) -> tuple:
    rec = item.record
    ordinal = rec.provenance.create_ord or 0
    origin = _origin(item.project_id, own)
    if rec.kind == KIND_WORK_ITEM:
        return (origin, _STATUS_RANK.get(rec.data.get("status"), 9), ordinal, rec.id)
    if rec.kind == KIND_ADR_DECISION:
        return (origin, -ordinal, rec.id)
    return (origin, ordinal, rec.id)


def _focus_lines(rec: Record, tag: str) -> list[str]:
    data = rec.data
    lines = [f"Goal: {one_line(data['goal'])}{tag}"]
    if data.get("branch"):
        lines.append(f"Branch: {one_line(data['branch'])}")
    if data.get("areas"):
        lines.append("Areas: " + ", ".join(one_line(a) for a in data["areas"]))
    if data.get("notes"):
        lines.append(f"Notes: {one_line(data['notes'])}")
    return lines


def _work_lines(rec: Record, tag: str) -> list[str]:
    data = rec.data
    lines = [f"- [{data['status']}] {one_line(data['title'])} ({rec.id}){tag}"]
    if data.get("detail"):
        lines.append(f"  {one_line(data['detail'])}")
    return lines


def _decision_lines(rec: Record, tag: str) -> list[str]:
    data = rec.data
    lines = [f"- {one_line(data['title'])} [{data['status']}] ({rec.id}){tag}: "
             f"{one_line(data['decision'])}",
             f"  Why: {one_line(data['context'])}"]
    for alt in data.get("rejected_alternatives") or []:
        lines.append(f"  Rejected: {one_line(alt['option'])}. "
                     f"Reason: {one_line(alt['reason'])}")
    return lines


def _constraint_lines(rec: Record, tag: str) -> list[str]:
    data = rec.data
    lines = [f"- [{data['category']}] {one_line(data['statement'])} ({rec.id}){tag}"]
    if data.get("reason"):
        lines.append(f"  Reason: {one_line(data['reason'])}")
    if data.get("applies_to"):
        lines.append("  Applies to: " + ", ".join(one_line(p) for p in data["applies_to"]))
    return lines


_FORMAT = {
    KIND_WORKSPACE_FOCUS: _focus_lines,
    KIND_WORK_ITEM: _work_lines,
    KIND_ADR_DECISION: _decision_lines,
    KIND_ENVIRONMENT_CONSTRAINT: _constraint_lines,
}


def collect(pool: list[TaggedRecord], own: str, *, has_file: bool = True
            ) -> tuple[list[BriefItem], list[Exclusion]]:
    """The brief items in priority order, and every pool record excluded by
    rule with the rule that excluded it. `has_file` is False for a target with
    no instruction file, where an instruction block goes nowhere."""
    kept: list[TaggedRecord] = []
    excluded: list[Exclusion] = []
    for item in pool:
        reason = _exclusion_reason(item.record, has_file)
        if reason is None:
            kept.append(item)
        else:
            excluded.append(Exclusion(item.project_id, item.record.kind,
                                      item.record.id, reason))
    items: list[BriefItem] = []
    for section in SECTIONS:
        members = [t for t in kept if _SECTION_OF[t.record.kind] == section]
        for t in sorted(members, key=lambda t: _sort_key(t, own)):
            lines = _FORMAT[t.record.kind](t.record, _tag(t.project_id, own))
            items.append(BriefItem(section, t.project_id, t.record, tuple(lines)))
    excluded.sort(key=lambda e: (e.project_id or "", e.kind, e.id))
    return items, excluded

"""validator_workspace.py -- semantic rules for the workspace-state kinds.

The three workspace-state kinds, and the one field W1 adds to a decision
record, get the same treatment validator.py gives the F0 kinds: required fields
with a type, enum-valued fields checked against their vocabulary, and optional
fields checked for shape only when present, so an old record without them stays
valid.

  workspace-focus         goal (required); areas, branch, notes (optional)
  work-item               title, status (required); detail (optional)
  environment-constraint  statement, category (required); reason, applies_to
  adr-decision            rejected_alternatives (optional): [{option, reason}]
  personality-block       applies_to (optional): [glob, ...]
"""
from __future__ import annotations

from .schema import (
    CONSTRAINT_CATEGORIES,
    KIND_ENVIRONMENT_CONSTRAINT,
    KIND_WORK_ITEM,
    KIND_WORKSPACE_FOCUS,
    WORK_ITEM_STATUSES,
    Record,
)

REQUIRED: dict[str, dict[str, type]] = {
    KIND_WORKSPACE_FOCUS: {"goal": str},
    KIND_WORK_ITEM: {"title": str, "status": str},
    KIND_ENVIRONMENT_CONSTRAINT: {"statement": str, "category": str},
}

_OPTIONAL_TEXT: dict[str, tuple[str, ...]] = {
    KIND_WORKSPACE_FOCUS: ("branch", "notes"),
    KIND_WORK_ITEM: ("detail",),
    KIND_ENVIRONMENT_CONSTRAINT: ("reason",),
}

_OPTIONAL_TEXT_LISTS: dict[str, tuple[str, ...]] = {
    KIND_WORKSPACE_FOCUS: ("areas",),
    KIND_ENVIRONMENT_CONSTRAINT: ("applies_to",),
}

_ENUMS: dict[str, tuple[str, tuple[str, ...]]] = {
    KIND_WORK_ITEM: ("status", WORK_ITEM_STATUSES),
    KIND_ENVIRONMENT_CONSTRAINT: ("category", CONSTRAINT_CATEGORIES),
}


def check_workspace_kind(rec: Record) -> list[str]:
    """Enum and optional-field checks for one workspace-state record. The
    required fields are checked by validator.py from REQUIRED."""
    problems: list[str] = []
    data = rec.data
    if rec.kind in _ENUMS:
        field, allowed = _ENUMS[rec.kind]
        if data.get(field) not in allowed:
            problems.append(
                f"{rec.kind}: {field} must be one of {list(allowed)}, "
                f"got {data.get(field)!r}")
    for field in _OPTIONAL_TEXT.get(rec.kind, ()):
        value = data.get(field)
        if value is not None and not isinstance(value, str):
            problems.append(f"{rec.kind}: {field} must be a string or null")
    for field in _OPTIONAL_TEXT_LISTS.get(rec.kind, ()):
        problems.extend(_text_list(rec.kind, field, data.get(field)))
    return problems


def _text_list(kind: str, field: str, value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(
            isinstance(item, str) and item for item in value):
        return [f"{kind}: {field} must be a list of non-empty strings"]
    return []


def check_applies_to(data: dict) -> list[str]:
    """`applies_to` on a personality block is optional; when present it is a
    non-empty list of glob patterns the region grammar can carry."""
    if "applies_to" not in data:
        return []
    from .textblock_scope import check_applies
    reason = check_applies(data["applies_to"])
    return [f"personality-block: {reason}"] if reason else []


def check_rejected_alternatives(data: dict) -> list[str]:
    """`rejected_alternatives` is optional. When present it is a list of
    objects carrying exactly a non-empty `option` and a non-empty `reason`, so
    an alternative is never recorded without the reason it was dropped."""
    value = data.get("rejected_alternatives")
    if value is None:
        return []
    label = "adr-decision: rejected_alternatives"
    if not isinstance(value, list):
        return [f"{label} must be a list"]
    problems: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict) or set(item) != {"option", "reason"}:
            problems.append(f"{label}[{index}] must carry exactly option and reason")
            continue
        for key in ("option", "reason"):
            if not isinstance(item[key], str) or not item[key].strip():
                problems.append(f"{label}[{index}].{key} must be non-empty text")
    return problems

"""authoring.py -- build the workspace-state records a person writes by hand.

Each builder returns a validated record in `workspace` scope with a provenance
receipt: harness `canon-cli`, a content hash over the kind and the payload, and
the next clock-free ordinal from the project's store. A builder that would
produce an invalid record raises AuthoringError with every problem at once.

Ids are stable and readable: `focus` (one per project), `task-<n>`,
`decision-<n>`, `constraint-<n>`. Updating a work item keeps its id and its
ordinal, so its place in a brief does not move when its status does.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

from canon.schema import (
    KIND_ADR_DECISION,
    KIND_ENVIRONMENT_CONSTRAINT,
    KIND_WORK_ITEM,
    KIND_WORKSPACE_FOCUS,
    SCOPE_WORKSPACE,
    Provenance,
    Record,
)
from canon.validator import validate_record
from canon.workspace.store import ProjectStore

HARNESS = "canon-cli"
FOCUS_ID = "focus"


class AuthoringError(ValueError):
    """The requested record would be invalid; the message lists why."""


def content_hash(kind: str, data: dict) -> str:
    payload = json.dumps({"kind": kind, "data": data}, sort_keys=True,
                         ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build(kind: str, rid: str, data: dict, create_ord: int, *,
          harness: str = HARNESS, source_hash: str | None = None,
          native_id: str | None = None, session_id: str | None = None) -> Record:
    """A validated workspace record, or AuthoringError listing every problem.
    An importer passes the digest of the source line as `source_hash`; a record
    written by hand is hashed over its own content."""
    clean = {k: v for k, v in data.items() if v is not None}
    record = Record(kind=kind, id=rid, scope=SCOPE_WORKSPACE, data=clean,
                    provenance=Provenance(
                        harness=harness,
                        source_hash=source_hash or content_hash(kind, clean),
                        native_id=native_id, session_id=session_id,
                        create_ord=create_ord))
    problems = validate_record(record)
    if problems:
        raise AuthoringError("; ".join(problems))
    return record


def current_branch(root: Path) -> str | None:
    """The branch named by the repository's HEAD, or None when HEAD is detached
    or there is no repository. Reads the file; runs no git command."""
    head = root / ".git"
    if head.is_file():
        text = head.read_text(encoding="utf-8").strip()
        if text.startswith("gitdir:"):
            target = Path(text[len("gitdir:"):].strip())
            head = target if target.is_absolute() else root / target
    head = head / "HEAD"
    if not head.is_file():
        return None
    ref = head.read_text(encoding="utf-8").strip()
    prefix = "ref: refs/heads/"
    return ref[len(prefix):] if ref.startswith(prefix) else None


def focus(store: ProjectStore, *, goal: str, areas: list[str] | None = None,
          branch: str | None = None, notes: str | None = None) -> Record:
    data = {"goal": goal, "areas": list(areas) if areas else None,
            "branch": branch, "notes": notes}
    return build(KIND_WORKSPACE_FOCUS, FOCUS_ID, data, store.next_ord())


def work_item(store: ProjectStore, *, title: str, status: str = "open",
              detail: str | None = None) -> Record:
    ordinal = store.next_ord()
    data = {"title": title, "status": status, "detail": detail}
    return build(KIND_WORK_ITEM, f"task-{ordinal}", data, ordinal)


def update_work_item(store: ProjectStore, rid: str, *, status: str | None = None,
                     detail: str | None = None) -> Record:
    """The same work item with a new status or detail, id and ordinal kept."""
    match = [r for r in store.records() if r.id == rid and r.kind == KIND_WORK_ITEM]
    if not match:
        raise AuthoringError(f"no work item with id {rid!r}")
    data = dict(match[0].data)
    if status is not None:
        data["status"] = status
    if detail is not None:
        data["detail"] = detail
    rebuilt = build(KIND_WORK_ITEM, rid, data, match[0].provenance.create_ord)
    return replace(rebuilt, temporal=match[0].temporal)


def decision(store: ProjectStore, *, title: str, decision_text: str, context: str,
             status: str = "accepted",
             rejected: list[tuple[str, str]] | None = None) -> Record:
    ordinal = store.next_ord()
    alternatives = [{"option": o, "reason": r} for o, r in (rejected or [])]
    data = {"title": title, "status": status, "context": context,
            "decision": decision_text,
            "rejected_alternatives": alternatives or None}
    return build(KIND_ADR_DECISION, f"decision-{ordinal}", data, ordinal)


def constraint(store: ProjectStore, *, statement: str, category: str = "constraint",
               reason: str | None = None,
               applies_to: list[str] | None = None) -> Record:
    ordinal = store.next_ord()
    data = {"statement": statement, "category": category, "reason": reason,
            "applies_to": list(applies_to) if applies_to else None}
    return build(KIND_ENVIRONMENT_CONSTRAINT, f"constraint-{ordinal}", data, ordinal)

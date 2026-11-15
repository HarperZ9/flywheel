"""moves.py -- the two explicit ways a record crosses a project boundary.

`promote` moves an accepted record from one project to global scope, where
every project reads it. `adopt` copies another project's accepted records into
this project, for the case the identity rules cannot see: a repository with no
remote that moved on disk, or a remote that was renamed. Both take a reason,
both write a log entry naming the other side, and neither runs on its own.
"""
from __future__ import annotations

from dataclasses import replace

from canon.schema import SCOPE_GLOBAL, SCOPE_WORKSPACE
from canon.workspace.rows import STATE_ACCEPTED, ProjectRow, encode_rows
from canon.workspace.store import (
    LOG_FILE,
    RECORDS_FILE,
    ProjectStore,
    StoreError,
    append_log,
    run_lock,
    write_atomic,
)


def _require_reason(reason: str) -> None:
    if not isinstance(reason, str) or not reason.strip():
        raise StoreError("this move needs a reason")


def promote(store: ProjectStore, record_id: str, *, reason: str) -> ProjectRow:
    """Move an accepted workspace record to global scope. The record leaves the
    project file, lands in the global file with `promoted_from` set, and both
    logs record the move and the reason. Refused, before anything is written,
    when global already holds a record with the same id: ids are per-project
    ordinals, so two projects meet on `constraint-1`, and replacing the global
    record would destroy the one another project put there."""
    _require_reason(reason)
    with store.locked(), run_lock(store.root, "canon-global"):
        accepted = store.rows(STATE_ACCEPTED)
        match = [r for r in accepted if r.record.id == record_id]
        if not match:
            raise StoreError(f"no accepted record with id {record_id!r}")
        record = replace(match[0].record, scope=SCOPE_GLOBAL)
        row = ProjectRow(None, STATE_ACCEPTED, record, None, store.project_id)
        global_rows = store.global_rows()
        existing = next((r for r in global_rows if r.key == row.key), None)
        if existing is not None:
            raise StoreError(
                f"global already holds {row.key[0]}/{row.key[1]} (promoted from "
                f"{existing.promoted_from}); nothing written")
        write_atomic(store.global_dir() / RECORDS_FILE,
                     encode_rows(global_rows + [row]))
        rest = [r for r in accepted if r is not match[0]]
        write_atomic(store.project_dir() / RECORDS_FILE, encode_rows(rest))
        detail = {"reason": reason, "from_project": store.project_id}
        store.log("promote", record, detail)
        append_log(store.global_dir() / LOG_FILE, "promote", record,
                   {**detail, "project_id": None}, store.clock())
    return row


def adopt(store: ProjectStore, from_project: str, *, reason: str) -> list[ProjectRow]:
    """Copy every accepted record of `from_project` into `store`'s project.
    Refuses before writing when any adopted (scope, id) already exists here,
    so an adoption never overwrites this project's own record."""
    _require_reason(reason)
    if from_project == store.project_id:
        raise StoreError("a project cannot adopt itself")
    source = ProjectStore(store.root, from_project)
    incoming = [r.record for r in source.rows(STATE_ACCEPTED)]
    if not incoming:
        raise StoreError(f"project {from_project} has no accepted records")
    with store.locked():
        store.ensure_manifest()
        own = {r.key for r in store.rows(STATE_ACCEPTED)}
        clashes = sorted(f"{r.scope}/{r.id}" for r in incoming
                         if (r.scope, r.id) in own)
        if clashes:
            raise StoreError(f"adoption would overwrite {clashes}; nothing written")
        rows = [ProjectRow(store.project_id, STATE_ACCEPTED,
                           replace(r, scope=SCOPE_WORKSPACE), None, None)
                for r in incoming]
        for row in rows:
            store.replace_row(row)
            store.log("adopt", row.record,
                      {"reason": reason, "from_project": from_project})
    return rows

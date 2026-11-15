"""Plan and apply a purge of captured context events.

A plan starts from a selection: one event, every event captured before an
ordinal (the audit sequence number of its put), every event in a workspace and
project, or a retention policy (context_retention.py). Its closure is each
selected event, the records derived from it at ingest, and the answer paired
with it, meaning an assistant event whose `responds_to` names it, because an
answer often restates its prompt; `keep_responses` leaves the answer. Events
that cite a purged event keep their own text, and their query results say the
cited event was purged. The plan digest binds the store, the scope, the
selection and every record the plan removes, so a confirmation applies exactly
the plan that was shown, and a plan the store has moved past is refused.

Apply works in one transaction on a connection with secure_delete on: it plans
again, compares the digest, deletes the records, appends a purge row and a
tombstone per record, marks the store scrub-pending, raises the identity
version and commits. Then it scrubs the files, clears the mark, scans them
(context_scrub.py) and reports what remains.

A selected event that an earlier purge removed is listed as already purged
rather than refused, so the owner can rerun a command that was interrupted. A
plan that removes nothing but finds the scrub mark still set finishes that
scrub when it is confirmed.
"""
from __future__ import annotations

import hashlib

from .canonical_json import canonical_json_bytes
from .context_audit import append_purge, verified_state
from .context_migrate import (
    checked_expected_store_id, compare_store_id, prepare_write, store_identity,
)
from .context_purge_report import nothing_report, plan_extras, purge_report, scrub_report
from .context_records import scope as checked_scope
from .context_scrub import (
    clear_scrub_mark, live_values, mark_scrub_pending, residual_scan, scan_values,
    scrub_complete, scrub_connection, scrub_database, scrub_pending, text_codec,
)
from .context_selection import (
    NOT_FOUND, REASON_OWNER, ContextPurgeError, ContextPurgeNotFound, ScopeView, Selection,
    Target, scope_view, select, was_purged,
)

__all__ = ["REASON_OWNER", "ContextPurgeError", "ContextPurgeNotFound", "ContextPurgeStale",
           "ScopeView", "Selection", "Target", "apply_purge", "build_plan", "plan_purge",
           "scope_view", "select", "was_purged"]

PLAN_SCHEMA = "canon.context-purge-plan/v1"
_ROLE_RANK = {"event": 0, "response": 1, "derived": 2}


class ContextPurgeStale(ContextPurgeError):
    """The confirmed plan no longer matches what the store holds."""


def plan_purge(store, workspace_id, project_id, selection, *, expected_store_id=None,
               local_detail=False) -> dict:
    workspace, project = checked_scope(workspace_id, project_id)
    expected = checked_expected_store_id(expected_store_id)
    with store._backend._conn() as conn:
        # A deferred read: a plan writes nothing to an established store, so a
        # reader holding the database does not block a dry run.
        conn.execute("BEGIN")
        store_id, version = store_identity(conn, create=True)
        compare_store_id(store_id, expected)
        state = verified_state(conn, version)
        pending = scrub_pending(conn)
    return build_plan(state, store_id, workspace, project, selection,
                      scrub_is_pending=pending, local_detail=local_detail)


def apply_purge(store, workspace_id, project_id, selection, *, confirm_plan_sha256,
                expected_store_id=None, busy_retry_seconds=30.0) -> dict:
    workspace, project = checked_scope(workspace_id, project_id)
    expected = checked_expected_store_id(expected_store_id)
    conn = scrub_connection(store.path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        store_id, version = store_identity(conn, create=True)
        compare_store_id(store_id, expected)
        state = verified_state(conn, version)
        plan = build_plan(state, store_id, workspace, project, selection,
                          scrub_is_pending=scrub_pending(conn))
        if confirm_plan_sha256 != plan["plan_sha256"]:
            raise ContextPurgeStale("context purge plan is stale; ask for a new plan")
        if not plan["entries"]:
            conn.rollback()
            if not plan["scrub_pending"]:
                return nothing_report(plan)
            return scrub_report(plan, _scrub(conn, busy_retry_seconds))
        values, short = scan_values([state.live[row["key"]].record for row in plan["entries"]])
        ordinals = _delete_and_tombstone(conn, plan["entries"])
        conn.commit()
        scrub = _scrub(conn, busy_retry_seconds)
        codec = text_codec(conn)
        scan = residual_scan(store.path, values, live_values(conn, codec), short, codec)
    finally:
        if conn.in_transaction:
            conn.rollback()
        conn.close()
    return purge_report(plan, ordinals, scrub, scan, store.verify_chain())


def build_plan(state, store_id, workspace, project, selection, *, scrub_is_pending=False,
               local_detail=False) -> dict:
    """The digest covers what the plan removes and what it found already
    purged. The scrub mark sits beside it: a scrub that finishes between plan
    and confirmation changes nothing the owner confirms."""
    view = scope_view(state, workspace, project)
    entries, already = _closure(view, selection.resolve(view), selection.keep_responses)
    roles = [row["role"] for row in entries]
    body = {"schema": PLAN_SCHEMA, "store_id": store_id, "workspace_id": workspace,
            "project_id": project, "selection": selection.description,
            "keep_responses": selection.keep_responses, "entries": entries,
            "already_purged": already,
            "counts": {"events": roles.count("event"), "responses": roles.count("response"),
                       "derived": roles.count("derived"), "records": len(entries)}}
    digest = "sha256:" + hashlib.sha256(canonical_json_bytes(body)).hexdigest()
    return {**body, "plan_sha256": digest, "scrub_pending": scrub_is_pending,
            **plan_extras(view, entries, local_detail)}


def _closure(view: ScopeView, targets: list[Target], keep_responses: bool):
    """The records a plan removes. A target an earlier purge removed is listed
    as already purged, and an answer stored after that purge still goes with
    it, so a rerun leaves nothing that restates the purged prompt."""
    entries: dict[str, dict] = {}
    already: set[str] = set()
    for target in sorted(targets, key=lambda item: (item.event_id, item.mode)):
        live = target.event_id in view.events
        if not live and not was_purged(view, target.event_id):
            raise ContextPurgeNotFound(NOT_FOUND)
        if not live:
            already.add(target.event_id)
        else:
            if target.mode != "derived":
                _add(entries, view, "workspace/" + target.event_id, target.event_id, "event",
                     target.reason_code)
            _add_derived(entries, view, target.event_id, target.reason_code)
        if target.mode == "derived" or keep_responses:
            continue
        for answer in view.answers.get(target.event_id, []):
            _add(entries, view, "workspace/" + answer, answer, "response", target.reason_code)
            _add_derived(entries, view, answer, target.reason_code)
    return [entries[key] for key in sorted(entries)], sorted(already)


def _add_derived(entries, view, event_id, reason_code) -> None:
    for key in view.derived.get(event_id, []):
        _add(entries, view, key, event_id, "derived", reason_code)


def _add(entries, view, key, event_id, role, reason_code) -> None:
    current = entries.get(key)
    if current is not None and _ROLE_RANK[current["role"]] <= _ROLE_RANK[role]:
        return
    entries[key] = {"key": key, "event_record_id": event_id, "role": role,
                    "reason_code": reason_code, "ordinal": view.state.live[key].ordinal}


def _scrub(conn, busy_retry_seconds: float) -> dict:
    """VACUUM and checkpoint, then clear the scrub mark if both finished."""
    scrub = scrub_database(conn, busy_retry_seconds)
    if scrub_complete(scrub):
        clear_scrub_mark(conn)
    scrub["pending"] = not scrub_complete(scrub)
    return scrub


def _delete_and_tombstone(conn, entries) -> list[int]:
    prepare_write(conn)
    mark_scrub_pending(conn)
    ordinals = []
    for row in entries:
        conn.execute("DELETE FROM records WHERE key=?", (row["key"],))
        ordinals.append(append_purge(conn, row["key"], row["reason_code"]))
    return ordinals

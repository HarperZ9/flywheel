"""Shared context operations over Canon's existing audited SQLite record store.

Every read and write reconciles the records with the op-aware audit chain in
one snapshot (context_audit.py). A put stores a salted commitment; a purge
(context_purge.py) removes records and leaves a tombstone per record; the
identity and schema versions are handled in context_migrate.py.

An event sent again after a purge removed it is stored again (D-155), and the
ingest result says `stored_after_purge` so the caller can tell the owner. A
get of a purged record says `purged` beside not found.

Every ingest is redacted first (context_redact.py), whoever sends it. An
answer, an assistant event whose `responds_to` names a prompt, is stored only
while that prompt is live in the same workspace and project. The check runs
inside the write transaction that stores the answer, so a purge of the prompt
cannot leave the answer behind (D-164).
"""
from __future__ import annotations

from pathlib import Path

from .backends.base import record_key
from .backends.sqlite import SqliteBackend
from .context_audit import ContextIntegrityError, insert_record, verified_state
from .context_migrate import (
    ContextStoreIdentityError,
    checked_expected_store_id,
    compare_store_id,
    prepare_write,
    read_version,
    store_identity,
)
from .context_query import search
from .context_records import LIMITS, make_records, scope
from .context_redact import redact_payload
from .context_related import mark_purged_citations, purged_citations

__all__ = ["ContextCollision", "ContextIntegrityError", "ContextPairingError", "ContextStore",
           "ContextStoreIdentityError"]


class ContextCollision(ValueError):
    """The same observed event identity was submitted with different content."""


class ContextPairingError(ValueError):
    """An answer names a prompt that is not live in this workspace and project."""

    def __init__(self, purged: bool) -> None:
        super().__init__("the prompt this answer responds to was purged" if purged else
                         "the prompt this answer responds to is not in the store")
        self.purged = purged


class ContextStore:
    def __init__(self, path):
        path = Path(path)
        if not path.is_absolute():
            raise ValueError("context database path must be absolute")
        self._backend = SqliteBackend(path)

    @property
    def path(self) -> Path:
        return Path(self._backend._path)

    def identity(self):
        with self._backend._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            return store_identity(conn, create=True)[0]

    def ingest(self, payload, expected_store_id=None):
        expected = checked_expected_store_id(expected_store_id)
        records = make_records(redact_payload(payload))
        with self._backend._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            store_id, version = store_identity(conn, create=True)
            compare_store_id(store_id, expected)
            state = verified_state(conn, version)
            first = state.live.get(record_key(records[0]))
            if first is not None:
                _check_redelivery(records, first, state)
                return self._ingest_result(records, "already_present", 0, store_id)
            if any(record_key(record) in state.live for record in records[1:]):
                raise ContextIntegrityError("captured event has derived records without its event")
            _require_prompt(records[0], state)
            prepare_write(conn)
            for record in records:
                insert_record(conn, record)
        status = "stored_after_purge" if record_key(records[0]) in state.purged else "stored"
        return self._ingest_result(records, status, len(records), store_id)

    @staticmethod
    def _ingest_result(records, status, count, store_id):
        return {"schema": "canon.context-ingest/v1", "status": status,
                "event_record_id": records[0].id, "records_stored": count,
                "source_hash": records[0].provenance.source_hash, "store_id": store_id,
                "does_not_prove": list(LIMITS)}

    def _records(self, workspace, project, expected_store_id=None):
        with self._backend._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            store_id, version = store_identity(conn, create=True)
            compare_store_id(store_id, checked_expected_store_id(expected_store_id))
            state = verified_state(conn, version)
        result = []
        for key in sorted(state.live):
            rec = state.live[key].record
            if (rec.data.get("workspace_id"), rec.data.get("project_id")) != (workspace, project):
                continue
            if rec.data.get("event_record_id"):
                result.append(rec)
        return result, store_id, state.purged_ids()

    def query(self, workspace_id, project_id, query, top_k=5, include_pending=True,
              expected_store_id=None, include_related=False, related_limit=5,
              exclude_answers=False):
        workspace, project = scope(workspace_id, project_id)
        records, store_id, purged = self._records(workspace, project, expected_store_id)
        result = search(records, workspace, project, query, top_k, include_pending,
                        include_related=include_related, related_limit=related_limit,
                        exclude_answers=exclude_answers)
        mark_purged_citations(result["hits"], records, purged)
        result["store_id"] = store_id
        return result

    def get(self, workspace_id, project_id, record_id, expected_store_id=None):
        workspace, project = scope(workspace_id, project_id)
        records, store_id, purged = self._records(workspace, project, expected_store_id)
        by_id = {rec.id: rec for rec in records}
        rec = by_id.get(record_id)
        if rec is None:
            missing = {"status": "not_found_in_searched_sources", "store_id": store_id,
                       "does_not_prove": list(LIMITS)}
            if record_id in purged:
                missing["purged"] = True
            return missing
        found = {"status": "found_in_searched_sources", "record_key": record_key(rec),
                 "record": rec.to_dict(), "store_id": store_id, "does_not_prove": list(LIMITS)}
        cited = purged_citations(rec, by_id, purged)
        if cited:
            found["cited_events_purged"] = cited
        return found

    def verify_chain(self):
        with self._backend._conn() as conn:
            conn.execute("BEGIN")
            length = conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0]
            try:
                verified_state(conn, read_version(conn))
            except ContextIntegrityError:
                return {"ok": False, "length": length}
            return {"ok": True, "length": length}

    def scrub_pending(self) -> bool:
        """Whether a purge committed and its file scrub has not finished."""
        from .context_scrub import scrub_pending
        with self._backend._conn() as conn:
            conn.execute("BEGIN")
            store_identity(conn, create=False)
            return scrub_pending(conn)

    def purge_plan(self, workspace_id, project_id, selection, *, expected_store_id=None,
                   local_detail=False):
        """The plan a purge of `selection` would apply; deletes nothing."""
        from .context_purge import plan_purge
        return plan_purge(self, workspace_id, project_id, selection,
                          expected_store_id=expected_store_id, local_detail=local_detail)

    def purge(self, workspace_id, project_id, selection, *, confirm_plan_sha256,
              expected_store_id=None, busy_retry_seconds=30.0):
        """Apply exactly the plan whose digest is `confirm_plan_sha256`."""
        from .context_purge import apply_purge
        return apply_purge(self, workspace_id, project_id, selection,
                           confirm_plan_sha256=confirm_plan_sha256,
                           expected_store_id=expected_store_id,
                           busy_retry_seconds=busy_retry_seconds)


def _require_prompt(event, state) -> None:
    """Refuse an answer whose prompt is not a live event in its scope."""
    data = event.data
    prompt = data.get("responds_to")
    if data.get("message_role") != "assistant" or not isinstance(prompt, str):
        return
    key = "workspace/" + prompt
    row = state.live.get(key)
    if row is None:
        raise ContextPairingError(purged=key in state.purged)
    found = row.record.data
    if (found.get("record_role"), found.get("workspace_id"), found.get("project_id")) != \
            ("event", data["workspace_id"], data["project_id"]):
        raise ContextPairingError(purged=False)


def _check_redelivery(records, first, state):
    """A redelivered event must match what is stored. Derived records a
    retention run purged stay purged."""
    if first.envelope != records[0].to_json():
        raise ContextCollision("event identity already exists with different content")
    for record in records[1:]:
        key = record_key(record)
        if key in state.purged:
            continue
        row = state.live.get(key)
        if row is None or row.envelope != record.to_json():
            raise ContextIntegrityError("captured event has missing or changed derived records")

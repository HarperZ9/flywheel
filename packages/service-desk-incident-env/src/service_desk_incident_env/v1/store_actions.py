"""Mutation and event-writing helpers for the ServiceDesk store."""
from __future__ import annotations

import json
from typing import Any

from harness.enterprise_envs.digest import canonical_json, digest, digest_text

from .descriptor import ENVIRONMENT_ID
from .store import EMPTY_SHA256, EVENT_TAG


def list_incidents(store: Any, token_ref: str, status: int = 200) -> dict[str, Any]:
    incidents = store.domain_state()["tables"]["incident"]
    response = {"status": status, "body": {"result": incidents}}
    store.record_event("GET", "/api/now/table/incident", {}, "", None, token_ref, True, "ok", False, response, {"applied": False})
    return response


def patch_incident(store: Any, sys_id: str, body: dict[str, Any], token_ref: str, idempotency_key: str | None = None) -> dict[str, Any]:
    cached = _cached_response(store, idempotency_key)
    return cached if cached is not None else _mutate_incident(store, sys_id, body, token_ref, idempotency_key)


def add_attachment(store: Any, body: dict[str, Any], token_ref: str, idempotency_key: str | None = None) -> dict[str, Any]:
    cached = _cached_response(store, idempotency_key)
    if cached is not None:
        return cached
    table = str(body.get("table_name", ""))
    record_id = str(body.get("record_id", ""))
    file_name = str(body.get("file_name", "attachment.txt"))
    content_sha = digest_text(str(body.get("content", "")))
    attachment_id = f"att_{content_sha[:12]}"
    return _mutate_attachment(store, table, record_id, file_name, content_sha, attachment_id, body, token_ref, idempotency_key)


def denied(store: Any, method: str, path_template: str, token_ref: str, status: int, reason: str) -> dict[str, Any]:
    response = {"status": status, "body": {"error": reason}}
    store.record_event(method, path_template, {}, "", None, token_ref, False, reason, False, response, {"applied": False})
    return response


def record_event(
    store: Any,
    method: str,
    path_template: str,
    path_params: dict[str, str],
    query: str,
    body: Any,
    token_ref: str,
    allowed: bool,
    reason: str,
    mutation_expected: bool,
    response: dict[str, Any],
    mutation: dict[str, Any],
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    with store._lock:
        store._conn.execute("BEGIN IMMEDIATE")
        try:
            before_sha = store.domain_state_sha256()
            seq = _next_seq(store)
            event = _event_body(store, seq, method, path_template, path_params, query, body, token_ref, allowed, reason, mutation, response, before_sha, before_sha)
            event_sha = digest(EVENT_TAG, event)
            store._conn.execute("INSERT INTO action_event(seq, event_sha256, event_json, idempotency_key) VALUES(?, ?, ?, ?)", (seq, event_sha, canonical_json(event), idempotency_key))
            store._conn.execute("COMMIT")
            return {"event_sha256": event_sha, "event": event, "response": response, "mutation_expected": mutation_expected}
        except Exception:
            store._conn.execute("ROLLBACK")
            raise


def _mutate_incident(store: Any, sys_id: str, body: dict[str, Any], token_ref: str, idempotency_key: str | None) -> dict[str, Any]:
    with store._lock:
        store._conn.execute("BEGIN IMMEDIATE")
        try:
            before_sha = store.domain_state_sha256()
            row = store._conn.execute("SELECT * FROM incident WHERE sys_id = ?", (sys_id,)).fetchone()
            if row is None:
                response = {"status": 404, "body": {"error": "incident_not_found"}}
                mutation: dict[str, Any] = {"applied": False}
            else:
                response, mutation = _apply_incident_update(store, row, sys_id, body, _next_seq(store))
            after_sha = store.domain_state_sha256()
            seq = _next_seq(store)
            event = _event_body(store, seq, "PATCH", "/api/now/table/incident/{sys_id}", {"sys_id": sys_id}, "", body, token_ref, True, "ok", mutation, response, before_sha, after_sha)
            _persist_event(store, seq, event, idempotency_key, response)
            store._conn.execute("COMMIT")
            return response
        except Exception:
            store._conn.execute("ROLLBACK")
            raise


def _apply_incident_update(store: Any, row: Any, sys_id: str, body: dict[str, Any], audit_seq: int) -> tuple[dict[str, Any], dict[str, Any]]:
    fields = {name: str(body[name]) for name in ("assignment_group", "priority", "cmdb_ci", "state") if name in body}
    work_note = str(body.get("work_note", "")).strip()
    field_changes = {name: {"before": row[name], "after": value} for name, value in fields.items() if row[name] != value}
    notes = list(json.loads(row["work_notes"]))
    if work_note:
        notes.append(work_note)
    if fields or work_note:
        store._conn.execute(
            "UPDATE incident SET assignment_group = ?, priority = ?, cmdb_ci = ?, state = ?, work_notes = ? WHERE sys_id = ?",
            (fields.get("assignment_group", row["assignment_group"]), fields.get("priority", row["priority"]), fields.get("cmdb_ci", row["cmdb_ci"]), fields.get("state", row["state"]), canonical_json(notes), sys_id),
        )
        store._set_meta("generation", str(int(store._meta("generation", "0") or "0") + 1))
    if field_changes:
        store._conn.execute(
            "INSERT INTO sys_audit(audit_id, table_name, record_id, field_changes, action_seq) VALUES(?, ?, ?, ?, ?)",
            (f"audit_{audit_seq:06d}", "incident", sys_id, canonical_json(field_changes), audit_seq),
        )
    record = store._conn.execute("SELECT * FROM incident WHERE sys_id = ?", (sys_id,)).fetchone()
    result = {**{key: record[key] for key in ("sys_id", "number", "short_description", "assignment_group", "priority", "state", "cmdb_ci")}, "work_notes": list(json.loads(record["work_notes"]))}
    response = {"status": 200, "body": {"result": result}}
    return response, {"applied": bool(fields or work_note), "table": "incident", "record_id": sys_id, "field_changes": field_changes}


def _mutate_attachment(store: Any, table: str, record_id: str, file_name: str, content_sha256: str, attachment_id: str, body: dict[str, Any], token_ref: str, idempotency_key: str | None) -> dict[str, Any]:
    with store._lock:
        store._conn.execute("BEGIN IMMEDIATE")
        try:
            before_sha = store.domain_state_sha256()
            exists = store._conn.execute("SELECT 1 FROM sys_attachment WHERE sys_id = ?", (attachment_id,)).fetchone() is not None
            if not exists:
                store._conn.execute(
                    "INSERT INTO sys_attachment(sys_id, table_name, record_id, file_name, content_sha256) VALUES(?, ?, ?, ?, ?)",
                    (attachment_id, table, record_id, file_name, content_sha256),
                )
                store._set_meta("generation", str(int(store._meta("generation", "0") or "0") + 1))
            result = {"sys_id": attachment_id, "table": table, "record_id": record_id, "file_name": file_name, "content_sha256": content_sha256}
            response = {"status": 201 if not exists else 200, "body": {"result": result}}
            mutation = {"applied": not exists, "table": "sys_attachment", "record_id": attachment_id, "target_table": table, "target_record_id": record_id, "field_changes": {}}
            after_sha = store.domain_state_sha256()
            seq = _next_seq(store)
            event = _event_body(store, seq, "POST", "/api/now/attachment/file", {}, "", body, token_ref, True, "ok", mutation, response, before_sha, after_sha)
            _persist_event(store, seq, event, idempotency_key, response)
            store._conn.execute("COMMIT")
            return response
        except Exception:
            store._conn.execute("ROLLBACK")
            raise


def _cached_response(store: Any, idempotency_key: str | None) -> dict[str, Any] | None:
    if not idempotency_key:
        return None
    with store._lock:
        row = store._conn.execute("SELECT response_json FROM idempotency WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
        return None if row is None else json.loads(row["response_json"])


def _persist_event(store: Any, seq: int, event: dict[str, Any], idempotency_key: str | None, response: dict[str, Any]) -> None:
    event_sha = digest(EVENT_TAG, event)
    store._conn.execute("INSERT INTO action_event(seq, event_sha256, event_json, idempotency_key) VALUES(?, ?, ?, ?)", (seq, event_sha, canonical_json(event), idempotency_key))
    if idempotency_key:
        store._conn.execute("INSERT INTO idempotency(idempotency_key, response_json, event_seq) VALUES(?, ?, ?)", (idempotency_key, canonical_json(response), seq))


def _event_body(store: Any, seq: int, method: str, path_template: str, path_params: dict[str, str], query: str, body: Any, token_ref: str, allowed: bool, reason: str, mutation: dict[str, Any], response: dict[str, Any], before_sha: str, after_sha: str) -> dict[str, Any]:
    return {
        "schema": "flywheel.enterprise-environment-action-event/v1",
        "environment_id": ENVIRONMENT_ID,
        "run_id": store.run_id,
        "instance_id": store.instance_id,
        "seq": seq,
        "request_id": f"req_{seq:06d}",
        "surface": "agent_api",
        "actor": {"role": "agent_itil", "token_ref": token_ref},
        "request": {"method": method, "path_template": path_template, "path_params": path_params, "query_sha256": digest_text(query), "body_sha256": EMPTY_SHA256 if body is None else digest_text(canonical_json(body))},
        "authorization": {"allowed": allowed, "reason": reason},
        "mutation": mutation,
        "response": {"status": response["status"], "body_sha256": digest_text(canonical_json(response["body"]))},
        "state": {"before_domain_state_sha256": before_sha, "after_domain_state_sha256": after_sha},
        "redaction": {"request_body_stored": False, "secret_values_present": False},
    }


def _next_seq(store: Any) -> int:
    return int(store._conn.execute("SELECT COALESCE(MAX(seq), 0) + 1 AS seq FROM action_event").fetchone()["seq"])

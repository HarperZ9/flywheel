"""SQLite state store and server-derived action log for ServiceDesk v1."""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from harness.enterprise_envs.digest import canonical_json, digest

from .descriptor import ENVIRONMENT_ID, descriptor_sha256
from .seed import seed_sha256, seed_tables

DOMAIN_TAG = "flywheel.enterprise-env.domain-state/v1"
EVENT_TAG = "flywheel.enterprise-env.action-event/v1"
LOG_TAG = "flywheel.enterprise-env.action-log/v1"
SNAPSHOT_TAG = "flywheel.enterprise-env.snapshot/v1"
EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


class ServiceDeskStore:
    def __init__(self, root: Path, run_id: str, instance_id: str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "state.sqlite3"
        self.run_id = run_id
        self.instance_id = instance_id
        self.descriptor_sha256 = descriptor_sha256()
        self.seed_sha256 = seed_sha256()
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, timeout=30, isolation_level=None, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._create_schema()
            if self._meta("seeded") != "true":
                self.reset(clear_action_log=True)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _create_schema(self) -> None:
        self._conn.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS cmdb_ci(sys_id TEXT PRIMARY KEY, name TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS incident(
                sys_id TEXT PRIMARY KEY, number TEXT NOT NULL, short_description TEXT NOT NULL,
                assignment_group TEXT NOT NULL, priority TEXT NOT NULL, state TEXT NOT NULL,
                cmdb_ci TEXT NOT NULL, work_notes TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sys_attachment(
                sys_id TEXT PRIMARY KEY, table_name TEXT NOT NULL, record_id TEXT NOT NULL,
                file_name TEXT NOT NULL, content_sha256 TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sys_audit(
                audit_id TEXT PRIMARY KEY, table_name TEXT NOT NULL, record_id TEXT NOT NULL,
                field_changes TEXT NOT NULL, action_seq INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS action_event(
                seq INTEGER PRIMARY KEY, event_sha256 TEXT NOT NULL, event_json TEXT NOT NULL,
                idempotency_key TEXT
            );
            CREATE TABLE IF NOT EXISTS idempotency(
                idempotency_key TEXT PRIMARY KEY, response_json TEXT NOT NULL, event_seq INTEGER NOT NULL
            );
            """
        )

    def _meta(self, key: str, default: str | None = None) -> str | None:
        row = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return default if row is None else str(row["value"])

    def _set_meta(self, key: str, value: str) -> None:
        self._conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)", (key, value))

    def reset(self, clear_action_log: bool = False) -> dict[str, Any]:
        with self._lock:
            generation_before = int(self._meta("generation", "0") or "0")
            before_sha = self.domain_state_sha256()
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                for table in ("cmdb_ci", "incident", "sys_attachment", "sys_audit"):
                    self._conn.execute(f"DELETE FROM {table}")
                if clear_action_log:
                    self._conn.execute("DELETE FROM action_event")
                    self._conn.execute("DELETE FROM idempotency")
                tables = seed_tables()
                self._conn.executemany("INSERT INTO cmdb_ci(sys_id, name) VALUES(?, ?)", [(r["sys_id"], r["name"]) for r in tables["cmdb_ci"]])
                rows = [
                    (
                        r["sys_id"], r["number"], r["short_description"], r["assignment_group"],
                        r["priority"], r["state"], r["cmdb_ci"], canonical_json(r["work_notes"]),
                    )
                    for r in tables["incident"]
                ]
                self._conn.executemany(
                    "INSERT INTO incident(sys_id, number, short_description, assignment_group, priority, state, cmdb_ci, work_notes) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                    rows,
                )
                self._set_meta("generation", "0")
                self._set_meta("seeded", "true")
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
            receipt = {
                "schema": "flywheel.enterprise-environment-reset-receipt/v1",
                "environment_id": ENVIRONMENT_ID,
                "run_id": self.run_id,
                "instance_id": self.instance_id,
                "generation_before": generation_before,
                "generation_after": 0,
                "before_domain_state_sha256": before_sha,
                "reset_domain_state_sha256": self.domain_state_sha256(),
                "seed_sha256": self.seed_sha256,
                "reset_method": "sqlite-transaction-seed-reload",
                "lock_result": "exclusive",
            }
            receipt["reset_receipt_sha256"] = digest("flywheel.enterprise-env.reset-receipt/v1", receipt)
            return receipt

    def domain_state(self) -> dict[str, Any]:
        with self._lock:
            incidents = []
            for row in self._conn.execute("SELECT sys_id, number, short_description, assignment_group, priority, state, cmdb_ci, work_notes FROM incident ORDER BY sys_id"):
                incidents.append({
                    **{key: row[key] for key in ("sys_id", "number", "short_description", "assignment_group", "priority", "state", "cmdb_ci")},
                    "work_notes": list(json.loads(row["work_notes"])),
                })
            tables = {
                "cmdb_ci": [dict(row) for row in self._conn.execute("SELECT sys_id, name FROM cmdb_ci ORDER BY sys_id")],
                "incident": incidents,
                "sys_attachment": [
                    {"sys_id": row["sys_id"], "table": row["table_name"], "record_id": row["record_id"], "file_name": row["file_name"], "content_sha256": row["content_sha256"]}
                    for row in self._conn.execute("SELECT sys_id, table_name, record_id, file_name, content_sha256 FROM sys_attachment ORDER BY sys_id")
                ],
                "sys_audit": [
                    {"audit_id": row["audit_id"], "table": row["table_name"], "record_id": row["record_id"], "field_changes": json.loads(row["field_changes"]), "action_seq": row["action_seq"]}
                    for row in self._conn.execute("SELECT audit_id, table_name, record_id, field_changes, action_seq FROM sys_audit ORDER BY action_seq, audit_id")
                ],
            }
            return {
                "schema": "flywheel.enterprise-environment-domain-state/v1",
                "environment_id": ENVIRONMENT_ID,
                "run_id": self.run_id,
                "instance_id": self.instance_id,
                "generation": int(self._meta("generation", "0") or "0"),
                "descriptor_sha256": self.descriptor_sha256,
                "seed_sha256": self.seed_sha256,
                "tables": tables,
            }

    def domain_state_sha256(self) -> str:
        return digest(DOMAIN_TAG, self.domain_state())

    def action_log(self) -> dict[str, Any]:
        with self._lock:
            rows = self._conn.execute("SELECT event_sha256, event_json FROM action_event ORDER BY seq")
            events = [{"event_sha256": row["event_sha256"], "event": json.loads(row["event_json"])} for row in rows]
            return {
                "schema": "flywheel.enterprise-environment-action-log/v1",
                "environment_id": ENVIRONMENT_ID,
                "run_id": self.run_id,
                "instance_id": self.instance_id,
                "descriptor_sha256": self.descriptor_sha256,
                "event_count": len(events),
                "events": events,
            }

    def action_log_sha256(self) -> str:
        return digest(LOG_TAG, self.action_log())

    def snapshot(self, kind: str) -> dict[str, Any]:
        state = self.domain_state()
        log = self.action_log()
        snapshot = {
            "schema": "flywheel.enterprise-environment-state-snapshot/v1",
            "environment_id": ENVIRONMENT_ID,
            "run_id": self.run_id,
            "instance_id": self.instance_id,
            "snapshot_kind": kind,
            "generation": state["generation"],
            "descriptor_sha256": self.descriptor_sha256,
            "seed_sha256": self.seed_sha256,
            "domain_state_sha256": digest(DOMAIN_TAG, state),
            "action_log_sha256": digest(LOG_TAG, log),
            "event_count": log["event_count"],
            "table_counts": {name: len(rows) for name, rows in state["tables"].items()},
        }
        snapshot["snapshot_sha256"] = digest(SNAPSHOT_TAG, snapshot)
        return snapshot

    def list_incidents(self, token_ref: str, status: int = 200) -> dict[str, Any]:
        from .store_actions import list_incidents
        return list_incidents(self, token_ref, status)

    def patch_incident(self, sys_id: str, body: dict[str, Any], token_ref: str, idempotency_key: str | None = None) -> dict[str, Any]:
        from .store_actions import patch_incident
        return patch_incident(self, sys_id, body, token_ref, idempotency_key)

    def add_attachment(self, body: dict[str, Any], token_ref: str, idempotency_key: str | None = None) -> dict[str, Any]:
        from .store_actions import add_attachment
        return add_attachment(self, body, token_ref, idempotency_key)

    def denied(self, method: str, path_template: str, token_ref: str, status: int, reason: str) -> dict[str, Any]:
        from .store_actions import denied
        return denied(self, method, path_template, token_ref, status, reason)

    def record_event(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        from .store_actions import record_event
        return record_event(self, *args, **kwargs)

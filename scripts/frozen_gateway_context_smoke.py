"""Canon context checks for the frozen gateway smoke."""
from __future__ import annotations

import json
import re
from pathlib import Path
import sqlite3
from typing import Callable

from harness.context_memory_bridge import (
    CAPTURE_RESULT_SCHEMA, CAPTURE_SCHEMA, PREFLIGHT_RESULT_SCHEMA,
    PREFLIGHT_SCHEMA, STATUS_SCHEMA)


WORKSPACE = "cdev"
PROJECT = "flywheel-mission"
ALIAS = "mission-memory"


def prepare_context_smoke_fixture(home: Path, owner_ref: str) -> dict[str, str]:
    return {
        "FLYWHEEL_CANON_CONTEXT_DB": str((home / "context-memory.sqlite").resolve()),
        "FLYWHEEL_CANON_CONTEXT_WORKSPACE_ID": WORKSPACE,
        "FLYWHEEL_CANON_CONTEXT_PROJECT_ID": PROJECT,
        "FLYWHEEL_CANON_CONTEXT_PROJECT_ALIASES": ALIAS,
        "FLYWHEEL_CANON_CONTEXT_OWNER_REFS": owner_ref,
        "FLYWHEEL_CANON_CONTEXT_TIMEOUT_MS": "10000",
    }


def run_context_memory_smoke(
        base: str, token: str, home: Path, owner_ref: str,
        secret_values: tuple[str, ...], request_fn: Callable,
        require: Callable[[bool, str], None]) -> dict:
    binding = _status_destination_binding(
        request_fn, base, token, secret_values, require)
    capture_request = {
        "schema": CAPTURE_SCHEMA,
        "project_ref": ALIAS,
        "config_generation": binding["config_generation"],
        "canon_store_id": binding["canon_store_id"],
        "event": {
            "event_id": "frozen-context-smoke-1",
            "source_app": "flywheel",
            "message_text": "Frozen context smoke captures canonical context.",
            "extractions": [{
                "source_id": "message",
                "text": "Frozen context smoke captures canonical context.",
                "claim_state": "reported_by_source",
            }],
        },
    }
    status, capture = _post_json(
        request_fn, base, "/api/context-memory/capture", token,
        body=capture_request, secret_values=secret_values)
    require(status == 200 and capture.get("status") in {"stored", "already_present"},
            "CONTEXT_CAPTURE_HTTP")
    expected_hash = _validate_capture_receipt(
        capture, capture_request, owner_ref, require)
    status, preflight = _post_json(
        request_fn, base, "/api/context-memory/preflight", token,
        body={"schema": PREFLIGHT_SCHEMA, "project_ref": ALIAS,
              "config_generation": binding["config_generation"],
              "canon_store_id": binding["canon_store_id"],
              "query": "canonical context"},
        secret_values=secret_values)
    require(status == 200 and preflight.get("status") == "found_in_searched_sources"
            and preflight.get("hits"), "CONTEXT_PREFLIGHT_HTTP")
    _validate_preflight_receipt(preflight, capture, expected_hash, owner_ref, require)
    status, denied = _post_json(
        request_fn, base, "/api/context-memory/preflight", token,
        body={"schema": PREFLIGHT_SCHEMA, "project_ref": "other-project",
              "config_generation": binding["config_generation"],
              "canon_store_id": binding["canon_store_id"],
              "query": "canonical context"}, secret_values=secret_values)
    require(status == 403 and denied.get("error", {}).get("code")
            == "CONTEXT_SCOPE_NOT_BOUND", "CONTEXT_DENIAL_PROMOTED")
    owner_denial = _deny_other_owner(
        request_fn, base, token, home, owner_ref, secret_values, require)
    _tamper_context_db(home, capture, require)
    status, tampered = _post_json(
        request_fn, base, "/api/context-memory/preflight", token,
        body={"schema": PREFLIGHT_SCHEMA, "project_ref": ALIAS,
              "config_generation": binding["config_generation"],
              "canon_store_id": binding["canon_store_id"],
              "query": "tampered evidence"}, secret_values=secret_values)
    require(status == 502 and tampered.get("error", {}).get("code")
            == "CANON_CONTEXT_TOOL_ERROR", "CONTEXT_TAMPER_ACCEPTED")
    return {
        "schema": "flywheel.frozen-context-memory-smoke/v1",
        "capture_status": capture.get("status"),
        "preflight_status": preflight.get("status"),
        "hit_count": len(preflight.get("hits") or []),
        "denied_project_code": denied.get("error", {}).get("code"),
        "denied_owner_code": owner_denial.get("error", {}).get("code"),
        "tampered_evidence_code": tampered.get("error", {}).get("code"),
        "event_record_id": capture.get("canon", {}).get("event_record_id"),
        "source_hash": expected_hash,
        "owner_ref_bound": owner_ref,
        "destination_binding_checked": True,
        "canon_store_id_bound": binding["canon_store_id"],
    }


def _post_json(request_fn, base: str, path: str, token: str, *,
               body: dict, secret_values: tuple[str, ...]) -> tuple[int, dict]:
    status, text = request_fn(
        base, path, token, body=body, secret_values=secret_values)
    try:
        return status, json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("CONTEXT_JSON_RESPONSE") from exc


def _status_destination_binding(request_fn, base: str, token: str,
                                secret_values: tuple[str, ...], require) -> dict:
    status, body = _post_json(
        request_fn, base, "/api/context-memory/status", token,
        body={}, secret_values=secret_values)
    require(status == 200 and body.get("schema") == STATUS_SCHEMA,
            "CONTEXT_STATUS_HTTP")
    require(body.get("destination_binding_configured") is True,
            "CONTEXT_DESTINATION_BINDING_MISSING")
    binding = body.get("destination_binding")
    require(isinstance(binding, dict), "CONTEXT_DESTINATION_BINDING_SHAPE")
    require(re.fullmatch(r"[0-9a-f]{64}", str(binding.get("config_generation") or "")),
            "CONTEXT_CONFIG_GENERATION_MISSING")
    require(re.fullmatch(r"ctxstore_[0-9a-f]{32}", str(binding.get("canon_store_id") or "")),
            "CONTEXT_STORE_ID_MISSING")
    require(binding.get("same_store_check") == "canon.expected_store_id.transaction/v1",
            "CONTEXT_STORE_CHECK_MISSING")
    return binding


def _validate_capture_receipt(capture: dict, request: dict, owner_ref: str,
                              require) -> str:
    canon = capture.get("canon")
    require(capture.get("schema") == CAPTURE_RESULT_SCHEMA, "CONTEXT_CAPTURE_SCHEMA")
    require(isinstance(canon, dict), "CONTEXT_CAPTURE_CANON_SHAPE")
    require(canon.get("schema") == "canon.context-ingest/v1",
            "CONTEXT_CAPTURE_CANON_SCHEMA")
    record_id = str(canon.get("event_record_id") or "")
    require(re.fullmatch(r"context-event-[0-9a-f]{64}", record_id) is not None,
            "CONTEXT_CAPTURE_EVENT_ID")
    source_hash = str(canon.get("source_hash") or "")
    event = dict(request["event"])
    event["owner_ref"], event["project_ref"] = owner_ref, ALIAS
    require(source_hash == _canon_hash(event), "CONTEXT_CAPTURE_SOURCE_HASH")
    return source_hash


def _validate_preflight_receipt(preflight: dict, capture: dict, source_hash: str,
                                owner_ref: str, require) -> None:
    require(preflight.get("schema") == PREFLIGHT_RESULT_SCHEMA,
            "CONTEXT_PREFLIGHT_SCHEMA")
    binding = preflight.get("scope_binding") or {}
    require(binding.get("owner_ref") == owner_ref, "CONTEXT_PREFLIGHT_OWNER")
    require(binding.get("canonical_project_id") == PROJECT,
            "CONTEXT_PREFLIGHT_PROJECT")
    require(preflight.get("canon", {}).get("schema") == "canon.context-query/v1",
            "CONTEXT_PREFLIGHT_CANON_SCHEMA")
    event_record_id = capture.get("canon", {}).get("event_record_id")
    citations = [
        hit.get("citation") or {} for hit in preflight.get("hits") or []
    ]
    require(any(c.get("event_record_id") == event_record_id
                and c.get("source_hash") == source_hash for c in citations),
            "CONTEXT_PREFLIGHT_RECEIPT_BINDING")


def _deny_other_owner(request_fn, base: str, token: str, home: Path,
                      owner_ref: str, secret_values: tuple[str, ...],
                      require) -> dict:
    path = home / "owner.ref"
    require(path.is_file(), "CONTEXT_OWNER_REF_MISSING")
    original = path.read_text(encoding="ascii")
    require(original == owner_ref, "CONTEXT_OWNER_REF_UNEXPECTED")
    other = "owner_" + ("b" * 32 if not owner_ref.endswith("b" * 32) else "c" * 32)
    path.write_text(other, encoding="ascii")
    try:
        status, denied = _post_json(
            request_fn, base, "/api/context-memory/preflight", token,
            body={"schema": PREFLIGHT_SCHEMA, "project_ref": ALIAS,
                  "query": "canonical context"}, secret_values=secret_values)
    finally:
        path.write_text(original, encoding="ascii")
    require(status == 403 and denied.get("error", {}).get("code")
            == "CONTEXT_OWNER_NOT_BOUND", "CONTEXT_OWNER_DENIAL_PROMOTED")
    return denied


def _tamper_context_db(home: Path, capture: dict, require) -> None:
    db = home / "context-memory.sqlite"
    require(db.is_file(), "CONTEXT_TAMPER_DB_MISSING")
    record_id = str((capture.get("canon") or {}).get("event_record_id") or "")
    require(record_id, "CONTEXT_TAMPER_RECORD_ID_MISSING")
    con = sqlite3.connect(str(db))
    try:
        count = con.execute(
            "SELECT COUNT(*) FROM records WHERE id=?", (record_id,)).fetchone()[0]
        require(count == 1, "CONTEXT_TAMPER_TARGET_MISSING")
        cur = con.execute("DELETE FROM records WHERE id=?", (record_id,))
        require(cur.rowcount == 1, "CONTEXT_TAMPER_DELETE_COUNT")
        con.commit()
    finally:
        con.close()


def _canon_hash(value: dict) -> str:
    return __import__("hashlib").sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False).encode()).hexdigest()

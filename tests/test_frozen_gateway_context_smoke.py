import json
import sqlite3
from hashlib import sha256
from pathlib import Path

from scripts.check_frozen_gateway import validate_canon_context_payload
from scripts.frozen_gateway_context_smoke import (
    prepare_context_smoke_fixture, run_context_memory_smoke)

OWNER = "owner_" + "a" * 32
GENERATION = "d" * 64
STORE_ID = "ctxstore_" + "1" * 32


def test_context_smoke_fixture_binds_absolute_db_and_owner(tmp_path):
    env = prepare_context_smoke_fixture(tmp_path, OWNER)

    assert Path(env["FLYWHEEL_CANON_CONTEXT_DB"]).is_absolute()
    assert env["FLYWHEEL_CANON_CONTEXT_WORKSPACE_ID"] == "cdev"
    assert env["FLYWHEEL_CANON_CONTEXT_PROJECT_ID"] == "flywheel-mission"
    assert env["FLYWHEEL_CANON_CONTEXT_PROJECT_ALIASES"] == "mission-memory"
    assert env["FLYWHEEL_CANON_CONTEXT_OWNER_REFS"] == OWNER


def test_context_memory_smoke_checks_roundtrip_denial_and_integrity(tmp_path):
    seen = []
    (tmp_path / "owner.ref").write_text(OWNER, encoding="ascii")
    _write_record(tmp_path, "context-event-" + "1" * 64)

    def request(_base, path, _token, *, body=None, secret_values=()):
        seen.append((path, body, secret_values))
        if path.endswith("/status"):
            return 200, json.dumps(_status())
        if (tmp_path / "owner.ref").read_text(encoding="ascii") != OWNER:
            return 403, '{"error":{"code":"CONTEXT_OWNER_NOT_BOUND"}}'
        assert body["config_generation"] == GENERATION
        assert body["canon_store_id"] == STORE_ID
        if body and body.get("project_ref") == "other-project":
            return 403, '{"error":{"code":"CONTEXT_SCOPE_NOT_BOUND"}}'
        if body and body.get("query") == "tampered evidence":
            return 502, '{"error":{"code":"CANON_CONTEXT_TOOL_ERROR"}}'
        if path.endswith("/capture"):
            event = dict(body["event"])
            event["owner_ref"], event["project_ref"] = OWNER, "mission-memory"
            source_hash = sha256(json.dumps(
                event, ensure_ascii=False, sort_keys=True,
                separators=(",", ":"), allow_nan=False).encode()).hexdigest()
            return 200, json.dumps({
                "schema": "flywheel.context-memory-capture/v1",
                "status": "stored",
                "canon": {"schema": "canon.context-ingest/v1",
                          "event_record_id": "context-event-" + "1" * 64,
                          "source_hash": source_hash},
            })
        return 200, json.dumps({
            "schema": "flywheel.context-memory-preflight/v1",
            "status": "found_in_searched_sources",
            "scope_binding": {"owner_ref": OWNER,
                              "canonical_project_id": "flywheel-mission"},
            "canon": {"schema": "canon.context-query/v1"},
            "hits": [{"excerpt": "frozen context",
                      "citation": {"event_record_id": "context-event-" + "1" * 64,
                                   "source_hash": result_source_hash(body)}}],
        })

    result = run_context_memory_smoke("http://127.0.0.1:1", "tok", tmp_path,
                                      OWNER, ("secret",), request, _require)

    assert result["capture_status"] == "stored"
    assert result["preflight_status"] == "found_in_searched_sources"
    assert result["denied_project_code"] == "CONTEXT_SCOPE_NOT_BOUND"
    assert result["denied_owner_code"] == "CONTEXT_OWNER_NOT_BOUND"
    assert result["tampered_evidence_code"] == "CANON_CONTEXT_TOOL_ERROR"
    assert result["destination_binding_checked"] is True
    assert result["canon_store_id_bound"] == STORE_ID
    assert [row[0] for row in seen] == [
        "/api/context-memory/status",
        "/api/context-memory/capture",
        "/api/context-memory/preflight",
        "/api/context-memory/preflight",
        "/api/context-memory/preflight",
        "/api/context-memory/preflight",
    ]


def test_context_memory_smoke_requires_actual_tamper_target(tmp_path):
    (tmp_path / "owner.ref").write_text(OWNER, encoding="ascii")

    def request(_base, path, _token, *, body=None, secret_values=()):
        if path.endswith("/status"):
            return 200, json.dumps(_status())
        if (tmp_path / "owner.ref").read_text(encoding="ascii") != OWNER:
            return 403, '{"error":{"code":"CONTEXT_OWNER_NOT_BOUND"}}'
        assert body["config_generation"] == GENERATION
        assert body["canon_store_id"] == STORE_ID
        if body and body.get("project_ref") == "other-project":
            return 403, '{"error":{"code":"CONTEXT_SCOPE_NOT_BOUND"}}'
        if path.endswith("/capture"):
            event = dict(body["event"])
            event["owner_ref"], event["project_ref"] = OWNER, "mission-memory"
            source_hash = sha256(json.dumps(
                event, ensure_ascii=False, sort_keys=True,
                separators=(",", ":"), allow_nan=False).encode()).hexdigest()
            return 200, json.dumps({
                "schema": "flywheel.context-memory-capture/v1",
                "status": "stored",
                "canon": {"schema": "canon.context-ingest/v1",
                          "event_record_id": "context-event-" + "2" * 64,
                          "source_hash": source_hash},
            })
        return 200, json.dumps({
            "schema": "flywheel.context-memory-preflight/v1",
            "status": "found_in_searched_sources",
            "scope_binding": {"owner_ref": OWNER,
                              "canonical_project_id": "flywheel-mission"},
            "canon": {"schema": "canon.context-query/v1"},
            "hits": [{"citation": {"event_record_id": "context-event-" + "2" * 64,
                                   "source_hash": result_source_hash(body)}}],
        })

    try:
        run_context_memory_smoke("http://127.0.0.1:1", "tok", tmp_path,
                                 OWNER, (), request, _require)
    except RuntimeError as exc:
        assert str(exc) == "CONTEXT_TAMPER_DB_MISSING"
    else:
        raise AssertionError("smoke accepted missing tamper database")


def test_frozen_smoke_validates_canon_payload_metadata(tmp_path):
    exe = tmp_path / "dist" / "flywheel-gateway" / "flywheel-gateway.exe"
    root = exe.parent / "_internal"
    (root / "packaging").mkdir(parents=True)
    (root / "python-lane-payloads" / "canon" / "licenses").mkdir(parents=True)
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_bytes(b"exe")
    license_data = b"Canon test license\n"
    license_hash = "sha256:" + sha256(license_data).hexdigest()
    (root / "python-lane-payloads" / "canon" / "licenses" / "LICENSE").write_bytes(
        license_data)
    row = {
        "lane": "canon",
        "owner_commit": "8c6a8228ce2117112c5dad74ddb0450ba80aa8ff",
        "component_descriptor": {"source": {"manifest_sha256": "sha256:" + "1" * 64}},
        "owner_project": {"license_files": [{
            "path": "LICENSE", "bytes": len(license_data), "sha256": license_hash}]},
    }
    (root / "packaging" / "python-lane-payloads.jsonl").write_text(
        json.dumps(row) + "\n", encoding="utf-8")

    result = validate_canon_context_payload(exe, _require)

    assert result["owner_commit"] == row["owner_commit"]
    assert result["license_sha256"] == license_hash
    assert result["license_present"] is True
    assert result["license_path"] == "python-lane-payloads/canon/licenses/LICENSE"
    assert not Path(result["license_path"]).is_absolute()
    assert ":" not in result["license_path"]


def _require(condition, code):
    if not condition:
        raise RuntimeError(code)


def _status():
    return {
        "schema": "flywheel.context-memory-status/v1",
        "destination_binding_configured": True,
        "destination_binding": {
            "schema": "flywheel.context-memory-destination-binding/v1",
            "config_generation": GENERATION,
            "canon_store_id": STORE_ID,
            "same_store_check": "canon.expected_store_id.transaction/v1",
        },
    }


def _write_record(tmp_path: Path, record_id: str):
    con = sqlite3.connect(str(tmp_path / "context-memory.sqlite"))
    try:
        con.execute("CREATE TABLE records("
                    "key TEXT PRIMARY KEY, scope TEXT, id TEXT, kind TEXT,"
                    "envelope TEXT, sha256 TEXT)")
        con.execute("CREATE TABLE audit("
                    "seq INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT,"
                    "sha256 TEXT, prev_hash TEXT, chain_hash TEXT)")
        con.execute("INSERT INTO records(key,scope,id,kind,envelope,sha256)"
                    "VALUES('k','workspace',?,'episodic','{}','abc')",
                    (record_id,))
        con.commit()
    finally:
        con.close()


def result_source_hash(body):
    # The capture hash is already validated against the submitted event; this
    # helper mirrors the single smoke event so the fake preflight can bind back.
    event = {
        "event_id": "frozen-context-smoke-1",
        "source_app": "flywheel",
        "message_text": "Frozen context smoke captures canonical context.",
        "extractions": [{
            "source_id": "message",
            "text": "Frozen context smoke captures canonical context.",
            "claim_state": "reported_by_source",
        }],
        "owner_ref": OWNER,
        "project_ref": "mission-memory",
    }
    return sha256(json.dumps(
        event, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()

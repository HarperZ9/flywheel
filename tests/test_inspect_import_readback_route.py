import hashlib
import json
import os
import sqlite3
from pathlib import Path

from harness.gateway_grant_route import gateway_grant_post
from harness.journey_store import JourneyStore, MutationCommand


OWNER = "owner_" + "a" * 32
OTHER = "owner_" + "b" * 32
JOURNEY = "jrn_" + "a" * 32
NOW = "2026-09-13T08:00:00Z"


class _Headers(dict):
    def get(self, key, default=None): return super().get(key, default)


class _Upload:
    MAX_BODY = 32 * 1024 * 1024
    def __init__(self, raw, headers, home, owner=OWNER):
        import io
        self.rfile = io.BytesIO(raw)
        self.headers = _Headers(headers)
        self.owner_ref, self.flywheel_home = owner, Path(home)
        self.root = "."
        self.clock = lambda: NOW
    def _content_length(self):
        try: value = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError): return None
        return None if value < 0 or value > self.MAX_BODY else value


class _Get:
    def __init__(self, home, owner=OWNER):
        self.flywheel_home = Path(home)
        self.owner_ref = owner


def _journey(state):
    return JourneyStore(state).create(MutationCommand(
        OWNER, JOURNEY, None, "create-1", "intake",
        {"legacy_label": None, "goal": "inspect import", "intake": {},
         "occurred_at": NOW})).event_head_sha256


def _grant(home, raw):
    state = Path(home) / "state"
    head, sha = _journey(state), hashlib.sha256(raw).hexdigest()
    op = {"source": {"kind": "client-upload", "format": "inspect-json",
                     "sha256": sha, "byte_length": len(raw),
                     "filename": "run.json"},
          "data_refs": [f"data_inspect.source:{sha[:32]}"],
          "credential_refs": []}
    proposal, status = gateway_grant_post(
        "/api/gateway-grants/prepare/import.inspect",
        json.dumps({"schema": "flywheel.gateway-operation/v1",
                    "journey_ref": JOURNEY, "expected_event_head": head,
                    "client_request_id": "inspect-1",
                    "operation": op}).encode(),
        owner_ref=OWNER, state_root=state, clock=lambda: NOW)
    assert status == 200
    approval, status = gateway_grant_post(
        "/api/gateway-grants/approve-once",
        json.dumps({"proposal_ref": proposal["proposal_ref"]}).encode(),
        owner_ref=OWNER, state_root=state, clock=lambda: NOW)
    assert status == 200
    return proposal, approval, op


def _headers(proposal, grant, op):
    source = op["source"]
    return {"Content-Type": "application/vnd.flywheel.inspect-json",
            "Content-Length": str(source["byte_length"]),
            "X-Flywheel-Journey-Ref": proposal["journey_ref"],
            "X-Flywheel-Expected-Event-Head": proposal["expected_event_head"],
            "X-Flywheel-Client-Request-Id": proposal["client_request_id"],
            "X-Flywheel-Grant-Ref": grant,
            "X-Flywheel-Inspect-Sha256": source["sha256"],
            "X-Flywheel-Inspect-Byte-Length": str(source["byte_length"]),
            "X-Flywheel-Inspect-Filename": "run.json"}


def _report(raw):
    sha = hashlib.sha256(raw).hexdigest()
    return {"schema": "flywheel.inspect-evidence/v1",
            "source": {"sha256": sha, "byte_length": len(raw)},
            "reported_status": "success", "assessment": "reported",
            "semantic_verification": "UNVERIFIABLE"}


def _upload(monkeypatch, home, raw=b'{"version":2}'):
    from harness.inspect_evidence_route import handle_inspect_upload
    proposal, approval, op = _grant(home, raw)
    monkeypatch.setattr("harness.inspect_evidence_route._import_inspect_log",
                        lambda data: _report(data))
    return handle_inspect_upload(_Upload(raw, _headers(proposal, approval["grant_ref"], op), home))


def _inspect_home(home, owner=OWNER):
    return Path(home) / "state" / "inspect-evidence" / owner


def _reseal_entity_data(db, eid, mutate):
    from harness.store import _sha
    with sqlite3.connect(str(db)) as conn:
        row = conn.execute("SELECT kind, project, data FROM entities WHERE eid=?",
                           (eid,)).fetchone()
        data = json.loads(row[2])
        mutate(data)
        sha = _sha({"kind": row[0], "project": row[1], "data": data})
        conn.execute("UPDATE entities SET data=?, sha256=? WHERE eid=?",
                     (json.dumps(data), sha, eid))


def test_upload_persists_owner_bound_wrapper_and_readback_survives_restart(monkeypatch, tmp_path):
    from harness.inspect_evidence_route import handle_inspect_get
    body, status = _upload(monkeypatch, tmp_path / "home")
    assert status == 200

    read, status = handle_inspect_get(
        f"/api/import/inspect/{body['stored']['eid']}", _Get(tmp_path / "home"), "")

    assert status == 200
    assert read == body
    assert not (tmp_path / "home" / "store.db").exists()
    assert (_inspect_home(tmp_path / "home") / "store.db").exists()


def test_list_is_bounded_owner_scoped_metadata_without_full_report(monkeypatch, tmp_path):
    from harness.inspect_evidence_route import handle_inspect_get
    first, _ = _upload(monkeypatch, tmp_path / "home", b'{"version":2,"n":1}')
    _upload(monkeypatch, tmp_path / "home", b'{"version":2,"n":2}')

    body, status = handle_inspect_get("/api/import/inspect", _Get(tmp_path / "home"), "limit=1&offset=1")

    assert status == 200 and body["schema"] == "flywheel.inspect-import-list/v1"
    assert body["limit"] == 1 and body["offset"] == 1 and len(body["items"]) == 1
    assert body["items"][0]["eid"] == first["stored"]["eid"]
    assert "report" not in body["items"][0]
    assert handle_inspect_get(f"/api/import/inspect/{first['stored']['eid']}", _Get(tmp_path / "home2"), "")[1] == 404
    assert handle_inspect_get(f"/api/import/inspect/{first['stored']['eid']}", _Get(tmp_path / "home", OTHER), "")[1] == 404


def test_list_verifies_chain_once_for_multiple_rows(monkeypatch, tmp_path):
    from harness.inspect_evidence_route import handle_inspect_get, verify_chain
    for i in range(3):
        _upload(monkeypatch, tmp_path / "home", f'{{"version":2,"n":{i}}}'.encode())
    calls = []
    def spy(*, home=None):
        calls.append(home)
        return verify_chain(home=home)
    monkeypatch.setattr("harness.inspect_evidence_route.verify_chain", spy)

    body, status = handle_inspect_get("/api/import/inspect", _Get(tmp_path / "home"), "limit=3")

    assert status == 200 and len(body["items"]) == 3
    assert calls == [_inspect_home(tmp_path / "home")]


def test_list_rejects_audit_chain_discontinuity(monkeypatch, tmp_path):
    from harness.inspect_evidence_route import handle_inspect_get
    for i in range(3):
        _upload(monkeypatch, tmp_path / "home", f'{{"version":2,"n":{i}}}'.encode())
    db = _inspect_home(tmp_path / "home") / "store.db"
    with sqlite3.connect(str(db)) as conn:
        seq, op, ref, sha = conn.execute(
            "SELECT seq, op, ref, sha256 FROM audit WHERE seq=2").fetchone()
        bad_prev = "f" * 64
        bad_chain = hashlib.sha256((bad_prev + op + ref + sha).encode()).hexdigest()
        conn.execute("UPDATE audit SET prev_hash=?, chain_hash=? WHERE seq=?",
                     (bad_prev, bad_chain, seq))

    body, status = handle_inspect_get("/api/import/inspect", _Get(tmp_path / "home"), "limit=3")

    assert status == 409
    assert body["error"]["code"] == "STORE_TAMPERED"


def test_tampered_store_row_is_typed_error(monkeypatch, tmp_path):
    from harness.inspect_evidence_route import handle_inspect_get
    body, _ = _upload(monkeypatch, tmp_path / "home")
    db = _inspect_home(tmp_path / "home") / "store.db"
    with sqlite3.connect(str(db)) as conn:
        row = conn.execute("SELECT data FROM entities WHERE eid=?", (body["stored"]["eid"],)).fetchone()[0]
        data = json.loads(row)
        data["result"]["source"]["sha256"] = "0" * 64
        conn.execute("UPDATE entities SET data=? WHERE eid=?",
                     (json.dumps(data), body["stored"]["eid"]))

    read, status = handle_inspect_get(f"/api/import/inspect/{body['stored']['eid']}", _Get(tmp_path / "home"), "")

    assert status == 409
    assert read["error"]["code"] == "STORE_TAMPERED"


def test_readback_rejects_resealed_source_shape_tamper(monkeypatch, tmp_path):
    from harness.inspect_evidence_route import handle_inspect_get
    body, _ = _upload(monkeypatch, tmp_path / "home")
    db = _inspect_home(tmp_path / "home") / "store.db"
    _reseal_entity_data(db, body["stored"]["eid"],
                        lambda data: data["result"]["source"].update(
                            {"client_path": "C:\\private\\run.json"}))

    read, status = handle_inspect_get(f"/api/import/inspect/{body['stored']['eid']}", _Get(tmp_path / "home"), "")

    assert status == 409
    assert read["error"]["code"] == "STORE_TAMPERED"


def test_readback_rejects_resealed_report_when_audit_attests_old_hash(monkeypatch, tmp_path):
    from harness.inspect_evidence_route import handle_inspect_get
    body, _ = _upload(monkeypatch, tmp_path / "home")
    db = _inspect_home(tmp_path / "home") / "store.db"
    _reseal_entity_data(db, body["stored"]["eid"],
                        lambda data: data["result"]["report"].update(
                            {"assessment": "incomplete"}))

    read, status = handle_inspect_get(f"/api/import/inspect/{body['stored']['eid']}", _Get(tmp_path / "home"), "")

    assert status == 409
    assert read["error"]["code"] == "STORE_TAMPERED"


def test_readback_rejects_entity_without_attesting_audit(monkeypatch, tmp_path):
    from harness.inspect_evidence_route import handle_inspect_get
    body, _ = _upload(monkeypatch, tmp_path / "home")
    db = _inspect_home(tmp_path / "home") / "store.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("DELETE FROM audit WHERE ref=?", (body["stored"]["eid"],))

    read, status = handle_inspect_get(f"/api/import/inspect/{body['stored']['eid']}", _Get(tmp_path / "home"), "")

    assert status == 409
    assert read["error"]["code"] == "STORE_TAMPERED"


def test_rejected_grant_and_ambient_home_do_not_write_inspect_store(monkeypatch, tmp_path):
    from harness.inspect_evidence_route import handle_inspect_upload
    ambient = tmp_path / "ambient"
    monkeypatch.setenv("FLYWHEEL_HOME", str(ambient))
    raw = b'{"version":2}'
    proposal, _approval, op = _grant(tmp_path / "home", raw)
    monkeypatch.setattr("harness.inspect_evidence_route._import_inspect_log",
                        lambda data: _report(data))
    upload = _Upload(raw, _headers(proposal, "gnt_" + "b" * 32, op), tmp_path / "home")

    body, status = handle_inspect_upload(upload)

    assert status == 403 and body["error"]["code"] == "PERMISSION_REQUIRED"
    assert not (_inspect_home(tmp_path / "home") / "store.db").exists()
    assert not (ambient / "store.db").exists()


def test_importer_source_identity_mismatch_rejects_before_storage(monkeypatch, tmp_path):
    from harness.inspect_evidence_route import handle_inspect_upload
    raw = b'{"version":2}'
    proposal, approval, op = _grant(tmp_path / "home", raw)
    wrong = _report(raw)
    wrong["source"]["sha256"] = "0" * 64
    monkeypatch.setattr("harness.inspect_evidence_route._import_inspect_log",
                        lambda _data: wrong)
    upload = _Upload(raw, _headers(proposal, approval["grant_ref"], op), tmp_path / "home")

    body, status = handle_inspect_upload(upload)

    assert status == 409
    assert body["error"]["code"] == "REPORT_SOURCE_MISMATCH"
    assert not (_inspect_home(tmp_path / "home") / "store.db").exists()

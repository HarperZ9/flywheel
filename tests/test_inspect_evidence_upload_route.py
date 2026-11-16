import hashlib
import io
import json

from harness.gateway_grant_route import gateway_grant_post
from harness.journey_store import JourneyStore, MutationCommand


OWNER = "owner_" + "a" * 32
JOURNEY = "jrn_" + "a" * 32
NOW = "2026-09-13T08:00:00Z"


class _Headers(dict):
    def get(self, key, default=None):
        return super().get(key, default)


class _ReadLog(io.BytesIO):
    def __init__(self, raw):
        super().__init__(raw)
        self.calls = 0

    def read(self, n=-1):
        self.calls += 1
        return super().read(n)


class _Upload:
    MAX_BODY = 32 * 1024 * 1024

    def __init__(self, raw, headers, home):
        self.rfile = _ReadLog(raw)
        self.headers = _Headers(headers)
        self.owner_ref = OWNER
        self.flywheel_home = home
        self.root = "."
        self.clock = lambda: NOW

    def _content_length(self):
        try:
            value = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            return None
        return None if value < 0 or value > self.MAX_BODY else value


def _journey(state):
    return JourneyStore(state).create(MutationCommand(
        OWNER, JOURNEY, None, "create-1", "intake",
        {"legacy_label": None, "goal": "inspect import", "intake": {},
         "occurred_at": NOW})).event_head_sha256


def _operation(raw, filename="run.json"):
    sha = hashlib.sha256(raw).hexdigest()
    return {
        "source": {"kind": "client-upload", "format": "inspect-json",
                   "sha256": sha, "byte_length": len(raw),
                   "filename": filename},
        "data_refs": [f"data_inspect.source:{sha[:32]}"],
        "credential_refs": [],
    }


def _grant(home, raw, filename="run.json"):
    state = home / "state"
    head = _journey(state)
    op = _operation(raw, filename)
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


def _headers(proposal, grant, op, *, content_length=None, sha=None, filename="run.json"):
    digest = sha or op["source"]["sha256"]
    length = op["source"]["byte_length"]
    return {
        "Content-Type": "application/vnd.flywheel.inspect-json",
        "Content-Length": str(length if content_length is None else content_length),
        "X-Flywheel-Journey-Ref": proposal["journey_ref"],
        "X-Flywheel-Expected-Event-Head": proposal["expected_event_head"],
        "X-Flywheel-Client-Request-Id": proposal["client_request_id"],
        "X-Flywheel-Grant-Ref": grant,
        "X-Flywheel-Inspect-Sha256": digest,
        "X-Flywheel-Inspect-Byte-Length": str(length),
        "X-Flywheel-Inspect-Filename": filename,
    }


def test_approved_exact_upload_returns_result_wrapper_and_store_receipt(monkeypatch, tmp_path):
    from harness.inspect_evidence_route import handle_inspect_upload

    raw = b'{"version":2,"status":"success","eval":{},"samples":[]}'
    proposal, approval, op = _grant(tmp_path / "home", raw)
    report = {"schema": "flywheel.inspect-evidence/v1",
              "source": {"sha256": op["source"]["sha256"],
                         "byte_length": len(raw)}}
    monkeypatch.setattr("harness.inspect_evidence_route._import_inspect_log",
                        lambda data: report)
    monkeypatch.setattr("harness.inspect_evidence_route.put_entity",
                        lambda kind, data, **_kw: {"eid": "eid1", "kind": kind,
                                                   "sha256": "s" * 64,
                                                   "chain_hash": "c" * 64})
    upload = _Upload(raw, _headers(proposal, approval["grant_ref"], op), tmp_path / "home")

    body, status = handle_inspect_upload(upload)

    assert status == 200
    assert body["schema"] == "flywheel.inspect-import-result/v1"
    assert body["source"]["sha256"] == op["source"]["sha256"]
    assert body["source"]["byte_length"] == len(raw)
    assert body["data_ref"] == f"data_inspect.source:{op['source']['sha256'][:32]}"
    assert body["report"] == report
    assert body["stored"]["kind"] == "inspect-evidence"


def test_digest_mismatch_rejects_before_import_or_store(monkeypatch, tmp_path):
    from harness.inspect_evidence_route import handle_inspect_upload

    raw = b'{"version":2}'
    proposal, approval, op = _grant(tmp_path / "home", raw)
    changed = b'{"version":3}'
    monkeypatch.setattr("harness.inspect_evidence_route._import_inspect_log",
                        lambda _raw: (_ for _ in ()).throw(AssertionError("parsed")))
    monkeypatch.setattr("harness.inspect_evidence_route.put_entity",
                        lambda *_args, **_kw: (_ for _ in ()).throw(AssertionError("stored")))
    upload = _Upload(changed, _headers(proposal, approval["grant_ref"], op,
                                       content_length=len(changed)), tmp_path / "home")

    body, status = handle_inspect_upload(upload)

    assert status == 409
    assert body["error"]["code"] == "SOURCE_DIGEST_MISMATCH"


def test_missing_grant_rejects_after_digest_without_import_or_store(monkeypatch, tmp_path):
    from harness.inspect_evidence_route import handle_inspect_upload

    raw = b'{"version":2}'
    proposal, _approval, op = _grant(tmp_path / "home", raw)
    monkeypatch.setattr("harness.inspect_evidence_route._import_inspect_log",
                        lambda _raw: (_ for _ in ()).throw(AssertionError("parsed")))
    monkeypatch.setattr("harness.inspect_evidence_route.put_entity",
                        lambda *_args, **_kw: (_ for _ in ()).throw(AssertionError("stored")))
    upload = _Upload(raw, _headers(proposal, "gnt_" + "b" * 32, op), tmp_path / "home")

    body, status = handle_inspect_upload(upload)

    assert status == 403
    assert body["error"]["code"] == "PERMISSION_REQUIRED"


def test_length_mismatch_rejects_without_reading_body(tmp_path):
    from harness.inspect_evidence_route import handle_inspect_upload

    raw = b"{}"
    proposal, approval, op = _grant(tmp_path / "home", raw)
    upload = _Upload(raw, _headers(proposal, approval["grant_ref"], op,
                                   content_length=len(raw) + 1), tmp_path / "home")

    body, status = handle_inspect_upload(upload)

    assert status == 400
    assert body["error"]["code"] == "INVALID_LENGTH"
    assert upload.rfile.calls == 0


def test_malformed_digest_header_rejects_without_reading_body(tmp_path):
    from harness.inspect_evidence_route import handle_inspect_upload

    raw = b"{}"
    proposal, approval, op = _grant(tmp_path / "home", raw)
    upload = _Upload(raw, _headers(proposal, approval["grant_ref"], op,
                                   sha=op["source"]["sha256"].upper()), tmp_path / "home")

    body, status = handle_inspect_upload(upload)

    assert status == 422
    assert body["error"]["code"] == "INVALID_REQUEST"
    assert upload.rfile.calls == 0


def test_filename_paths_are_rejected_before_authorization(tmp_path):
    from harness.inspect_evidence_route import handle_inspect_upload

    raw = b"{}"
    proposal, approval, op = _grant(tmp_path / "home", raw)
    upload = _Upload(raw, _headers(proposal, approval["grant_ref"], op,
                                   filename="C:/secret/run.json"), tmp_path / "home")

    body, status = handle_inspect_upload(upload)

    assert status == 422
    assert body["error"]["code"] == "INVALID_REQUEST"

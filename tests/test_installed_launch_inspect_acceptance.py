import json
import sqlite3
from pathlib import Path

from desktop.tool import installed_launch_acceptance as ila
from tests.installed_launch_acceptance_fixtures import (
    TOKEN, FakeProcess, FakeWindows, build_manifest, make_install,
    status_doc, valid_registry, write_token,
)

INSPECT_ROWS = (
    "H21_inspect_fixture_hash_bound",
    "H22_inspect_journey_seeded_in_isolated_profile",
    "H23_inspect_grant_prepare_approve_bound_to_upload",
    "H24_inspect_upload_exact_bytes_accepted",
    "H25_inspect_false_success_controls_rejected",
    "H26_inspect_reopen_after_engine_restart_matches_upload",
    "H27_inspect_list_redacts_report_and_names_eid",
    "H28_inspect_store_tamper_detected",
    "H29_inspect_api_receipt_does_not_claim_desktop_ui",
)


def test_inspect_mode_imports_restarts_reopens_and_labels_api_only(tmp_path):
    install, app_sha, engine_sha = make_install(tmp_path)
    token_path = write_token(tmp_path)
    fixture = Path(__file__).parents[1] / "tests/fixtures/inspect/v1/single-success.fixture.json"
    http = InspectHttp(token_path.parents[0])

    receipt = run_inspect_harness(
        tmp_path, install, fixture, http,
        expected_app_sha256=app_sha, expected_engine_sha256=engine_sha,
        build_manifest=build_manifest(tmp_path, install, app_sha=app_sha, engine_sha=engine_sha),
        artifact_root=token_path.parents[1],
    )

    assert receipt["complete"] is True
    assert receipt["mode"] == "inspect"
    assert all(ila.assertion_state(receipt, row_id) == "PASS" for row_id in INSPECT_ROWS)
    assert http.upload_headers["Content-Type"] == "application/json"
    assert http.upload_headers["Content-Length"] == str(len(http.uploaded_raw))
    assert http.changed_source_rejected is True
    assert http.missing_grant_rejected is True
    assert http.missing_bearer_checked is True
    assert http.reopened_after_tamper is True
    assert len(http.status_calls) == 2
    assert json.dumps(receipt).find(TOKEN) == -1
    assert any("file-picker" in item for item in receipt["does_not_prove"])
    api_row = row(receipt, "H29_inspect_api_receipt_does_not_claim_desktop_ui")
    assert api_row["observed_redacted"] == {
        "api_only": True,
        "native_ui_launched": False,
        "desktop_file_picker_exercised": False,
    }


def test_inspect_mode_fails_closed_when_changed_source_control_passes(tmp_path):
    install, app_sha, engine_sha = make_install(tmp_path)
    token_path = write_token(tmp_path)
    fixture = Path(__file__).parents[1] / "tests/fixtures/inspect/v1/single-success.fixture.json"
    http = InspectHttp(token_path.parents[0], accept_changed_source=True)

    receipt = run_inspect_harness(
        tmp_path, install, fixture, http,
        expected_app_sha256=app_sha, expected_engine_sha256=engine_sha,
        build_manifest=build_manifest(tmp_path, install, app_sha=app_sha, engine_sha=engine_sha),
        artifact_root=token_path.parents[1],
    )

    assert receipt["complete"] is False
    assert ila.assertion_state(receipt, "H25_inspect_false_success_controls_rejected") == "FAIL"


def test_inspect_mode_fails_closed_when_changed_source_rejected_for_unrelated_reason(tmp_path):
    install, app_sha, engine_sha = make_install(tmp_path)
    token_path = write_token(tmp_path)
    fixture = Path(__file__).parents[1] / "tests/fixtures/inspect/v1/single-success.fixture.json"
    http = InspectHttp(token_path.parents[0], changed_source_error="ALREADY_CONSUMED")

    receipt = run_inspect_harness(
        tmp_path, install, fixture, http,
        expected_app_sha256=app_sha, expected_engine_sha256=engine_sha,
        build_manifest=build_manifest(tmp_path, install, app_sha=app_sha, engine_sha=engine_sha),
        artifact_root=token_path.parents[1],
    )

    assert receipt["complete"] is False
    control = row(receipt, "H25_inspect_false_success_controls_rejected")
    assert control["state"] == "FAIL"
    assert control["observed_redacted"]["changed_source_error_code"] == "ALREADY_CONSUMED"


def test_inspect_mode_fails_when_prepare_omits_binding_fields(tmp_path):
    install, app_sha, engine_sha = make_install(tmp_path)
    token_path = write_token(tmp_path)
    fixture = Path(__file__).parents[1] / "tests/fixtures/inspect/v1/single-success.fixture.json"
    http = InspectHttp(token_path.parents[0], omit_prepare_binding=True)

    receipt = run_inspect_harness(
        tmp_path, install, fixture, http,
        expected_app_sha256=app_sha, expected_engine_sha256=engine_sha,
        build_manifest=build_manifest(tmp_path, install, app_sha=app_sha, engine_sha=engine_sha),
        artifact_root=token_path.parents[1],
    )

    assert receipt["complete"] is False
    grant = row(receipt, "H23_inspect_grant_prepare_approve_bound_to_upload")
    assert grant["state"] == "FAIL"
    assert grant["observed_redacted"]["source_bound"] is False


def test_inspect_receipt_semantics_reject_missing_api_only_label(tmp_path):
    receipt = {
        "schema": ila.SCHEMA,
        "run_id": "run-a",
        "complete": True,
        "mode": "inspect",
        "assertions": [
            {"id": aid, "state": "PASS", "severity": "critical"}
            for aid in ila.ASSERTION_IDS
            if aid != "H29_inspect_api_receipt_does_not_claim_desktop_ui"
        ],
        "phase_results": [
            {"id": pid, "state": "RECORDED", "assertion_ids": list(ila.PHASE_ASSERTIONS[pid])}
            for pid in ila.PHASE_IDS
        ],
    }
    path = tmp_path / "missing-api-label.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")

    try:
        ila.verify_receipt_file(path, "run-a")
    except ila.ReceiptError as exc:
        assert "H29_inspect_api_receipt_does_not_claim_desktop_ui" in str(exc)
    else:
        raise AssertionError("accepted inspect receipt without API-only boundary row")


def run_inspect_harness(tmp_path, install, fixture, http, **overrides):
    values = {
        "install_root": install,
        "out": tmp_path / "receipt.json",
        "run_id": "run-inspect",
        "source_commit_expected": "276d399d37485ca63815cea1e629db06f123e839",
        "expected_version": "0.6.1",
        "mode": "inspect",
        "start_engine": True,
        "inspect_import": True,
        "inspect_fixture": fixture,
    }
    values.update(overrides)
    cfg = ila.HarnessConfig(**values)
    return ila.AcceptanceHarness(
        cfg,
        fs=ila.LocalFilesystem(),
        windows=FakeWindows(registry=valid_registry(install)),
        http=http,
        process=FakeProcess(),
        clock=ila.FixedClock("2026-09-13T00:00:00Z"),
    ).run()


def row(receipt, row_id):
    return next(item for item in receipt["assertions"] if item["id"] == row_id)


class InspectHttp:
    def __init__(self, home: Path, *, accept_changed_source=False,
                 changed_source_error="SOURCE_DIGEST_MISMATCH",
                 omit_prepare_binding=False):
        self.home = Path(home)
        self.accept_changed_source = accept_changed_source
        self.changed_source_error = changed_source_error
        self.omit_prepare_binding = omit_prepare_binding
        self.status_calls = []
        self.upload_headers = {}
        self.uploaded_raw = b""
        self.uploaded_body = None
        self.changed_source_rejected = False
        self.missing_grant_rejected = False
        self.missing_bearer_checked = False
        self.reopened_after_tamper = False
        self.eid = "eid-inspect-1"
        self.store = {}
        self.prepare_count = 0

    def get_json(self, url, token=None, timeout=2.0):
        if url.endswith("/api/desktop/status"):
            self.status_calls.append(url)
            return 200, status_doc()
        if url.endswith("/api/import/inspect") and token is None:
            self.missing_bearer_checked = True
            return 401, {"schema": "flywheel.evidence-transport-error/v1", "error": {"code": "AUTH_REQUIRED"}}
        if url.endswith(f"/api/import/inspect/{self.eid}"):
            if self._store_source_hash_tampered():
                self.reopened_after_tamper = True
                return 409, {"schema": "flywheel.evidence-transport-error/v1", "error": {"code": "STORE_TAMPERED"}}
            return 200, self.uploaded_body
        if "/api/import/inspect?limit=" in url:
            return 200, {
                "schema": "flywheel.inspect-import-list/v1",
                "items": [{
                    "eid": eid,
                    "source": body["source"],
                    "reported_status": "success",
                    "assessment": "reported",
                    "stored": body["stored"],
                } for eid, body in self.store.items()],
                "limit": 10,
                "offset": 0,
            }
        raise AssertionError(f"unexpected GET {url}")

    def post_json(self, url, payload, token=None, timeout=2.0):
        if url.endswith("/api/gateway-grants/prepare/import.inspect"):
            self.prepare_count += 1
            source = payload["operation"]["source"]
            suffix = f"{self.prepare_count:032x}"
            body = {
                "schema": "flywheel.gateway-grant-proposal/v1",
                "proposal_ref": "prp_" + suffix,
                "planned_grant_ref": "gnt_" + suffix,
                "action": "import.inspect",
                "journey_ref": payload["journey_ref"],
                "expected_event_head": payload["expected_event_head"],
                "client_request_id": payload["client_request_id"],
                "destination": {"kind": "import", "ref": f"inspect-json:{source['sha256'][:16]}"},
                "data_refs": [f"data_inspect.source:{source['sha256'][:32]}"],
                "scopes": ["write"],
                "operation_sha256": "a" * 64,
                "arguments_sha256": "b" * 64,
            }
            if self.omit_prepare_binding:
                body.pop("destination")
                body.pop("data_refs")
            return 200, body
        if url.endswith("/api/gateway-grants/approve-once"):
            return 200, {"grant_ref": "gnt_" + payload["proposal_ref"][4:]}
        raise AssertionError(f"unexpected POST {url} {payload}")

    def post_bytes(self, url, raw, headers, token=None, timeout=20.0):
        if not url.endswith("/api/import/inspect"):
            raise AssertionError(f"unexpected raw POST {url}")
        if int(headers.get("Content-Length", "-1")) != len(raw):
            return 400, {"schema": "flywheel.evidence-transport-error/v1", "error": {"code": "INVALID_LENGTH"}}
        if not headers.get("X-Flywheel-Grant-Ref") or headers.get("X-Flywheel-Grant-Ref") == "gnt_" + "f" * 32:
            self.missing_grant_rejected = True
            return 403, {"schema": "flywheel.evidence-transport-error/v1", "error": {"code": "PERMISSION_REQUIRED"}}
        declared = headers["X-Flywheel-Inspect-Sha256"]
        import hashlib
        actual = hashlib.sha256(raw).hexdigest()
        if actual != declared and not self.accept_changed_source:
            self.changed_source_rejected = self.changed_source_error == "SOURCE_DIGEST_MISMATCH"
            return 409, {"schema": "flywheel.evidence-transport-error/v1", "error": {"code": self.changed_source_error}}
        if actual != declared and self.accept_changed_source:
            body = self._body(raw, actual, eid=f"eid-inspect-{len(self.store) + 1}")
            self._write_store(body)
            return 200, body
        self.upload_headers = dict(headers)
        self.uploaded_raw = raw
        self.uploaded_body = self._body(raw, actual, eid=self.eid)
        self._write_store(self.uploaded_body)
        return 200, self.uploaded_body

    def _body(self, raw, sha, eid=None):
        eid = eid or self.eid
        return {
            "schema": "flywheel.inspect-import-result/v1",
            "source": {"format": "inspect-json", "sha256": sha,
                       "byte_length": len(raw), "filename": "single-success.fixture.json"},
            "data_ref": f"data_inspect.source:{sha[:32]}",
            "report": {"schema": "flywheel.inspect-evidence/v1",
                       "source": {"sha256": sha, "byte_length": len(raw)},
                       "producer": {"format": "inspect-json", "version": 2},
                       "reported_status": "success", "assessment": "reported",
                       "invalidated": False,
                       "semantic_verification": "UNVERIFIABLE"},
            "stored": {"kind": "inspect-evidence", "eid": eid,
                       "sha256": "d" * 64, "chain_hash": "e" * 64},
        }

    def _write_store(self, body):
        owner = (self.home / "owner.ref").read_text(encoding="ascii")
        db = self.home / "state" / "inspect-evidence" / owner / "store.db"
        db.parent.mkdir(parents=True, exist_ok=True)
        self.store[body["stored"]["eid"]] = body
        with sqlite3.connect(str(db)) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS entities (eid TEXT PRIMARY KEY, data TEXT)")
            conn.execute("INSERT OR REPLACE INTO entities VALUES (?, ?)",
                         (body["stored"]["eid"], json.dumps({"result": body})))

    def _store_source_hash_tampered(self):
        owner = (self.home / "owner.ref").read_text(encoding="ascii")
        db = self.home / "state" / "inspect-evidence" / owner / "store.db"
        with sqlite3.connect(str(db)) as conn:
            row = conn.execute("SELECT data FROM entities WHERE eid=?", (self.eid,)).fetchone()
        data = json.loads(row[0])
        return data["result"]["source"]["sha256"] == "0" * 64

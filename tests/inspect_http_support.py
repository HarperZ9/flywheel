from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from harness import gateway
from harness.evidence_json import canonical_bytes
from harness.journey_store import JourneyStore, MutationCommand


OWNER = "owner_" + "a" * 32
JOURNEY = "jrn_" + "a" * 32
NOW = "2026-09-13T08:00:00Z"
REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "inspect" / "v1" / "single-success.fixture.json"
INSPECT_UPLOAD_CONTENT_TYPE = "application/json"


def projected_inspect_log() -> bytes:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return canonical_bytes(fixture["inspect_log"])


def inspect_operation(raw: bytes, filename: str = "single-success.fixture.json") -> dict:
    sha = hashlib.sha256(raw).hexdigest()
    return {
        "source": {
            "kind": "client-upload",
            "format": "inspect-json",
            "sha256": sha,
            "byte_length": len(raw),
            "filename": filename,
        },
        "data_refs": [f"data_inspect.source:{sha[:32]}"],
        "credential_refs": [],
    }


class InspectGateway:
    def __init__(self, tmp_path, monkeypatch):
        self.home = Path(tmp_path) / "gateway-home"
        self.run_root = Path(tmp_path) / "run-root"
        self.ambient_home = Path(tmp_path) / "ambient-home"
        self.token = secrets.token_urlsafe(32)
        self._server = None
        self._thread = None
        self._head = None
        self.port = None
        monkeypatch.setenv("FLYWHEEL_HOME", str(self.ambient_home))
        self.home.mkdir(parents=True)
        self.run_root.mkdir()
        (self.home / "owner.ref").write_text(OWNER, encoding="ascii")

    def start(self):
        class Handler(gateway._Handler):
            pass

        Handler.root = REPO
        Handler.run_root = str(self.run_root)
        Handler.flywheel_home = self.home
        Handler.auth_token = self.token
        Handler.allowed_hosts = gateway.DEFAULT_HOSTS
        Handler.clock = staticmethod(lambda: NOW)
        Handler.owner_ref = None
        Handler.operation_service = None
        Handler.operation_process_factory = None
        Handler.session_token_store = None
        Handler._session_token_state_root = None
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self._server.server_port
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=20)
        self._server = None
        self._thread = None
        self.port = None

    def restart(self):
        self.stop()
        return self.start()

    def close(self):
        self.stop()

    def request(self, method: str, path: str, body: bytes | None = None,
                headers: dict | None = None, *, bearer: bool = True):
        req_headers = dict(headers or {})
        if bearer:
            req_headers["Authorization"] = "Bearer " + self.token
        conn = HTTPConnection("127.0.0.1", self.port, timeout=20)
        try:
            conn.request(method, path, body=body, headers=req_headers)
            response = conn.getresponse()
            raw = response.read()
            return response.status, json.loads(raw.decode("utf-8"))
        finally:
            conn.close()

    def post_json(self, path: str, body: dict, *, bearer: bool = True):
        raw = json.dumps(body, separators=(",", ":")).encode("utf-8")
        return self.request("POST", path, raw, {"Content-Type": "application/json"},
                            bearer=bearer)

    def get_json(self, path: str, *, bearer: bool = True):
        return self.request("GET", path, bearer=bearer)

    def ensure_journey(self):
        if self._head:
            return self._head
        state = self.home / "state"
        ack = JourneyStore(state).create(MutationCommand(
            OWNER, JOURNEY, None, "create-inspect", "intake",
            {"legacy_label": None, "goal": "inspect import", "intake": {},
             "occurred_at": NOW}))
        self._head = ack.event_head_sha256
        return self._head

    def prepare_import(self, raw: bytes, request_id: str):
        body = {
            "schema": "flywheel.gateway-operation/v1",
            "journey_ref": JOURNEY,
            "expected_event_head": self.ensure_journey(),
            "client_request_id": request_id,
            "operation": inspect_operation(raw),
        }
        return self.post_json("/api/gateway-grants/prepare/import.inspect", body)

    def approve(self, proposal: dict):
        return self.post_json("/api/gateway-grants/approve-once",
                              {"proposal_ref": proposal["proposal_ref"]})

    def read_proposal(self, proposal: dict):
        return self.post_json("/api/gateway-grants/read", {
            "schema": "flywheel.gateway-grant-read-request/v1",
            "proposal_ref": proposal["proposal_ref"],
        })

    def reject(self, proposal: dict):
        status, read = self.read_proposal(proposal)
        assert status == 200
        return self.post_json("/api/gateway-grants/reject", {
            "schema": "flywheel.gateway-grant-reject-request/v1",
            "proposal_ref": proposal["proposal_ref"],
            "expected_record_sha256": read["record_sha256"],
        })

    def upload(self, raw: bytes, proposal: dict, grant_ref: str,
               filename: str = "single-success.fixture.json"):
        op = inspect_operation(raw, filename)
        source = op["source"]
        headers = {
            "Content-Type": INSPECT_UPLOAD_CONTENT_TYPE,
            "X-Flywheel-Journey-Ref": proposal["journey_ref"],
            "X-Flywheel-Expected-Event-Head": proposal["expected_event_head"],
            "X-Flywheel-Client-Request-Id": proposal["client_request_id"],
            "X-Flywheel-Grant-Ref": grant_ref,
            "X-Flywheel-Inspect-Sha256": source["sha256"],
            "X-Flywheel-Inspect-Byte-Length": str(source["byte_length"]),
            "X-Flywheel-Inspect-Filename": filename,
        }
        return self.request("POST", "/api/import/inspect", raw, headers)

    def inspect_store(self):
        return self.home / "state" / "inspect-evidence" / OWNER / "store.db"

    def tamper_source_hash(self, eid: str):
        with sqlite3.connect(str(self.inspect_store())) as conn:
            row = conn.execute(
                "SELECT data FROM entities WHERE eid=?", (eid,)).fetchone()
            data = json.loads(row[0])
            data["result"]["source"]["sha256"] = "0" * 64
            conn.execute("UPDATE entities SET data=? WHERE eid=?",
                         (json.dumps(data), eid))

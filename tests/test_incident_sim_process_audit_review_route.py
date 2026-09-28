from __future__ import annotations

import hashlib
import io
import json

from harness.institutional_access import access_scope
from harness.incident_sim_packet import build_process_audit_packet
from tests.test_incident_sim_packet import TASK, _access_record, trace

PATH = "/api/incident-sim/process-audit/review"


class _Headers(dict):
    def get(self, key, default=None):
        return super().get(key, default)


class _ReadLog(io.BytesIO):
    def __init__(self, raw: bytes):
        super().__init__(raw)
        self.calls = []

    def read(self, n=-1):
        before = self.tell()
        out = super().read(n)
        self.calls.append((n, before, self.tell(), len(out)))
        return out


def _raw_packet(packet: dict | None = None) -> bytes:
    return json.dumps(
        packet or build_process_audit_packet(TASK, trace()),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _post(raw: bytes, *, content_type: str = "application/json"):
    from harness.incident_sim_process_audit_route import process_audit_review_post

    return process_audit_review_post(PATH, raw, content_type=content_type)


def test_review_route_reports_raw_source_integrity_and_packet_local_limits():
    raw = _raw_packet()

    body, status = _post(raw)

    assert status == 200
    assert body["schema"] == "flywheel.incident-sim-process-audit-review/v1"
    assert body["source"] == {
        "format": "incident-sim-process-audit-json",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "byte_length": len(raw),
    }
    assert body["verification"]["verdict"] == "MATCH"
    assert body["declared_access"]["verdict"] == "NOT_ASSESSED"
    assert any("component absent" in item for item in body["declared_access"]["limits"])
    assert any("coherent rewrite" in item for item in body["does_not_prove"])
    pointers = {row["json_pointer"]: row["source_value"] for row in body["source_pointers"]}
    assert pointers["/evaluation/overall/verdict"] == "MATCH"
    assert pointers["/source_values"]
    assert pointers["/independence"]["roles"] == TASK["roles"]


def test_review_route_reports_tampered_packet_as_drift_without_semantic_pass():
    packet = build_process_audit_packet(TASK, trace())
    packet["evaluation"]["overall"]["verdict"] = "FORGED"

    body, status = _post(_raw_packet(packet))

    assert status == 200
    assert body["verification"]["verdict"] == "DRIFT"
    assert body["assessment"] == "packet-local-drift"
    assert body["semantic_verification"] == "UNVERIFIABLE"


def test_review_route_reports_malformed_access_component_as_drift_not_500():
    packet = build_process_audit_packet(TASK, trace())
    packet["institutional_access"] = {
        "schema": "flywheel.institutional-access-component/v1",
        "context": "synthetic_declared_access",
        "assessment": {"claims": [{"coverage": ["malformed"]}]},
        "component_sha256": "0" * 64,
    }

    body, status = _post(_raw_packet(packet))

    assert status == 200
    assert body["verification"]["verdict"] == "DRIFT"
    assert body["declared_access"]["coverage_assessment"] == "unknown"


def test_review_route_does_not_promote_drifted_reported_access_coverage():
    good = trace()
    scope = access_scope("incident-sim-synthetic", {"claim-final-state": ["task", "trace"]},
                         {"task": TASK, "trace": good})
    packet = build_process_audit_packet(
        TASK,
        good,
        institutional_access=_access_record(scope),
        institutional_access_scope=scope,
    )
    assert packet["institutional_access"]["assessment"]["coverage_assessment"] == "complete"
    packet["institutional_access"]["component_sha256"] = "0" * 64

    body, status = _post(_raw_packet(packet))

    assert status == 200
    access = body["declared_access"]
    assert access["verdict"] == "DRIFT"
    assert access["reported_coverage_assessment"] == "complete"
    assert access["coverage_assessment"] == "unknown"
    assert any("untrusted" in item for item in access["limits"])


def test_review_route_rejects_malformed_duplicate_nonfinite_and_wrong_media_type():
    duplicate, status = _post(b'{"schema":"x","schema":"y"}')
    assert status == 400
    assert duplicate["error"]["code"] == "INVALID_JSON"

    nonfinite, status = _post(b'{"value":NaN}')
    assert status == 400
    assert nonfinite["error"]["code"] == "INVALID_JSON"

    media, status = _post(b"{}", content_type="text/plain")
    assert status == 415
    assert media["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"


def test_review_route_rejects_oversized_body():
    body, status = _post(b'{"pad":"' + b"x" * (1024 * 1024) + b'"}')

    assert status == 413
    assert body["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_gateway_dispatches_private_process_audit_review_once(monkeypatch, tmp_path):
    from harness import gateway
    from harness.gateway_custody import is_private
    from harness.route_inventory import gateway_routes

    raw = _raw_packet()
    stream = _ReadLog(raw)
    handler = gateway._Handler.__new__(gateway._Handler)
    handler.path = PATH
    handler.run_root = tmp_path / "run"
    handler.flywheel_home = tmp_path / "home"
    handler.root = tmp_path / "root"
    handler.owner_ref = "owner_" + "a" * 32
    handler.headers = _Headers({
        "Content-Length": str(len(raw)),
        "Content-Type": "application/json; charset=utf-8",
    })
    handler.rfile = stream
    sent = {}
    seen = []

    monkeypatch.setattr(
        "harness.incident_sim_process_audit_route.process_audit_review_post",
        lambda path, body, *, content_type: (
            seen.append((path, body, content_type))
            or ({"schema": "route-witness/v1"}, 209)
        ),
    )
    handler._json = lambda body, code=200: sent.update(body=body, code=code)

    handler._post()

    assert sent == {"body": {"schema": "route-witness/v1"}, "code": 209}
    assert seen == [(PATH, raw, "application/json; charset=utf-8")]
    assert stream.calls == [(len(raw), 0, len(raw), len(raw))]
    assert is_private(PATH)
    routes = {route.path: route for route in gateway_routes()}
    assert routes[PATH].methods == ("POST",)
    assert routes[PATH].description == "review incident-sim process-audit packet"


def test_gateway_rejects_oversized_process_audit_review_without_reading(tmp_path):
    from harness import gateway

    raw = b"{}"
    stream = _ReadLog(raw)
    handler = gateway._Handler.__new__(gateway._Handler)
    handler.path = PATH
    handler.headers = _Headers({
        "Content-Length": str(1024 * 1024 + 1),
        "Content-Type": "application/json",
    })
    handler.rfile = stream
    handler._json = lambda body, code=200: setattr(handler, "sent", (body, code))

    handler._post()

    body, status = handler.sent
    assert status == 413
    assert body["error"]["code"] == "PAYLOAD_TOO_LARGE"
    assert stream.calls == []


def test_gateway_private_auth_refuses_review_route_before_dispatch(tmp_path):
    from harness import gateway

    handler = gateway._Handler.__new__(gateway._Handler)
    handler.path = PATH
    handler.command = "POST"
    handler.auth_token = ""
    handler.allowed_hosts = gateway.DEFAULT_HOSTS
    handler.flywheel_home = tmp_path / "home"
    handler.headers = _Headers({"Host": "localhost", "Content-Type": "application/json"})
    handler.wfile = io.BytesIO()
    statuses = []
    handler.send_response = statuses.append
    handler.send_header = lambda *_args: None
    handler.end_headers = lambda: None

    assert handler._authorized() is False
    body = json.loads(handler.wfile.getvalue())
    assert statuses == [401]
    assert body["error"]["code"] == "AUTH_REQUIRED"


def test_review_route_does_not_create_state_files(tmp_path, monkeypatch):
    from harness import gateway

    raw = _raw_packet()
    handler = gateway._Handler.__new__(gateway._Handler)
    handler.path = PATH
    handler.run_root = tmp_path / "run"
    handler.flywheel_home = tmp_path / "home"
    handler.root = tmp_path / "root"
    handler.owner_ref = "owner_" + "a" * 32
    handler.headers = _Headers({"Content-Length": str(len(raw)), "Content-Type": "application/json"})
    handler.rfile = io.BytesIO(raw)
    handler._json = lambda body, code=200: setattr(handler, "sent", (body, code))

    before = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*"))
    handler._post()
    after = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*"))

    assert handler.sent[1] == 200
    assert after == before

import io
import json

from harness import gateway
from harness.gateway_custody import is_private
from harness.studio_body_contract import CONTRACT_VERSION, SOUND_ACTION_KIND, SOUND_TARGET_PREFIX


class _Headers:
    def __init__(self, cl):
        self._cl = cl

    def get(self, key, default=None):
        return self._cl if key == "Content-Length" else default


def _handler(tmp_path, path):
    h = gateway._Handler.__new__(gateway._Handler)
    h.path = path
    h.root = "."
    h.run_root = str(tmp_path)
    h.flywheel_home = tmp_path
    h.clock = lambda: "2026-09-15T12:00:00Z"
    return h


def _post(tmp_path, path, body):
    raw = json.dumps(body).encode("utf-8")
    h = _handler(tmp_path, path)
    h.headers = _Headers(str(len(raw)))
    h.rfile = io.BytesIO(raw)
    sent = {}
    h._json = lambda b, code=200: sent.update(body=b, code=code)
    h._post()
    return sent


def _get(tmp_path, path):
    h = _handler(tmp_path, path)
    sent = {}
    h._json = lambda b, code=200: sent.update(body=b, code=code)
    h._get()
    return sent


def _step():
    return {
        "schema": CONTRACT_VERSION,
        "client_action_id": "client-1",
        "idempotency_key": "idem-1",
        "model_route_ref": "deterministic-stub/v1",
        "observation_ref": "obs_seed",
        "action": {
            "kind": SOUND_ACTION_KIND,
            "target": SOUND_TARGET_PREFIX + "session-1/instrument-1",
            "args": {"seed": 58, "duration_s": 6.0, "root_hz": 220.0},
        },
    }


def test_body_routes_are_private_custody():
    assert is_private("/api/studio/body/status")
    assert is_private("/api/studio/body/step")


def test_gateway_body_status_route_reports_unconfigured_authority(tmp_path, monkeypatch):
    monkeypatch.delenv("ACCOUNTABLE_SURFACE_GRANTS", raising=False)
    monkeypatch.delenv("ACCOUNTABLE_SURFACE_AUTHORITY_STATE", raising=False)

    sent = _get(tmp_path, "/api/studio/body/status")

    assert sent["code"] == 200
    assert sent["body"]["body_contract_version"] == CONTRACT_VERSION
    assert sent["body"]["backend_ready"] is False
    assert sent["body"]["built"]["routes"] is True
    assert sent["body"]["verified"]["usable_grant"] is False
    assert sent["body"]["authority"]["grant_required"] is True


def test_gateway_body_step_refuses_without_authority_configuration(tmp_path, monkeypatch):
    monkeypatch.delenv("ACCOUNTABLE_SURFACE_GRANTS", raising=False)
    monkeypatch.delenv("ACCOUNTABLE_SURFACE_AUTHORITY_STATE", raising=False)

    sent = _post(tmp_path, "/api/studio/body/step", _step())

    assert sent["code"] == 503
    assert sent["body"]["accepted"] is False
    assert sent["body"]["status"] == "authority_unconfigured"
    assert sent["body"]["action_kind"] == SOUND_ACTION_KIND


def test_gateway_body_step_rejects_malformed_numeric_defaults(tmp_path):
    body = _step()
    body["action"]["args"]["seed"] = "58"

    sent = _post(tmp_path, "/api/studio/body/step", body)

    assert sent["code"] == 400
    assert sent["body"]["accepted"] is False
    assert sent["body"]["status"] == "invalid_request"


def test_gateway_body_snapshot_requires_explicit_session_and_instrument(tmp_path):
    sent = _post(tmp_path, "/api/studio/body/snapshot", {})

    assert sent["code"] == 400
    assert sent["body"]["error"] == "session_ref must be a stable ref without slashes"


def test_gateway_body_snapshot_marks_requested_frame_refs_unchecked(tmp_path):
    sent = _post(tmp_path, "/api/studio/body/snapshot", {
        "session_ref": "session-1",
        "instrument_ref": "instrument-1",
        "capture_session_ref": "cap-main",
        "source_ref": "display:primary",
        "latest_frame_ref": "display:primary:7",
        "latest_delivered_frame_age_ms": 42,
    })

    snapshot = sent["body"]["snapshot"]
    assert sent["code"] == 200
    assert snapshot["latest_frame_ref"] is None
    assert snapshot["capture"]["available"] is False
    assert snapshot["requested_capture"]["latest_frame_ref"] == "display:primary:7"
    assert snapshot["requested_capture"]["validated"] is False


def test_gateway_body_step_rejects_unverified_frame_refs_before_authority(tmp_path, monkeypatch):
    monkeypatch.delenv("ACCOUNTABLE_SURFACE_GRANTS", raising=False)
    body = _step()
    body["latest_frame_ref"] = "frame-0007"
    body["model_delivery"] = {"parts": [{"kind": "image", "frame_ref": "frame-0007"}]}

    sent = _post(tmp_path, "/api/studio/body/step", body)

    assert sent["code"] == 503
    assert sent["body"]["accepted"] is False
    assert sent["body"]["status"] == "capture_evidence_unverified"

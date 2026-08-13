import io
import json
import socket
import urllib.request

import pytest

from harness import gateway
from harness.evidence_journey import append_event, new_journey, run_journey_check
from harness.evidence_route import evidence_post


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _journey():
    journey = new_journey(
        journey_id="journey-transport-v1",
        goal="Explain the failed check",
        intake={"summary": "a bounded metadata record", "source_refs": ["raw/input.txt"]},
        created_at="2026-08-12T12:00:00Z",
    )
    return append_event(journey, {
        "stage": "decomposed", "occurred_at": "2026-08-12T12:01:00Z",
        "claims": [{"claim_id": "claim-root", "statement": "The check failed",
                    "depends_on": [], "verdict": "UNDECIDED",
                    "reason": "checker has not run", "receipt_refs": []}],
    })


def _context(candidate_ref="candidate.py"):
    return {"task_id": "transport-v1", "prompt": "Check the submitted artifact",
            "oracle_cmd": "python -m pytest test_candidate.py",
            "candidate_ref": candidate_ref,
            "raw_artifact_refs": [candidate_ref, "test_candidate.py"],
            "timeout_seconds": 5}


def _post(root, action, body):
    return evidence_post(f"/api/evidence/{action}",
                         json.dumps(body).encode("utf-8"), root=root)


def test_start_and_project_transport_only_server_owned_facts(tmp_path):
    _write_json(tmp_path / "meta" / "intake.json", {"summary": "failed", "count": 1})
    started, code = _post(tmp_path, "start", {
        "journey_id": "journey-1", "goal": "Explain the failure",
        "created_at": "2026-08-12T12:00:00Z", "intake_ref": "meta/intake.json",
    })
    assert code == 200 and started["schema"] == "flywheel.evidence-journey/v1"
    assert started["intake"] == {"count": 1, "summary": "failed"}
    _write_json(tmp_path / "journey.json", _journey())
    projected, code = _post(tmp_path, "project", {
        "journey_ref": "journey.json", "lens": "Rescue",
    })
    assert code == 200 and projected["lens"] == "Rescue"
    assert projected["journey_id"] == "journey-transport-v1"
    rendered = json.dumps([started, projected])
    assert str(tmp_path) not in rendered and "traceback" not in rendered.lower()


@pytest.mark.parametrize("intake", [
    {"summary": "failed", "api_key": "do-not-emit"},
    {"summary": "failed", "openai_api_key": "do-not-emit"},
    {"summary": "failed", "nested": {"password": "do-not-emit"}},
    {"summary": "failed", "source": "C:/Users/private/raw.txt"},
    {"summary": "failed", "source_refs": ["../private/raw.txt"]},
])
def test_start_rejects_secret_or_host_path_metadata(tmp_path, intake):
    _write_json(tmp_path / "intake.json", intake)
    result, code = _post(tmp_path, "start", {
        "journey_id": "journey-1", "goal": "Explain the failure",
        "created_at": "2026-08-12T12:00:00Z", "intake_ref": "intake.json",
    })
    rendered = json.dumps(result)
    assert code == 422 and result["error"]["code"] == "UNSAFE_METADATA"
    assert "do-not-emit" not in rendered and str(tmp_path) not in rendered


def test_start_rejects_oversized_metadata_with_typed_response(tmp_path):
    path = tmp_path / "intake.json"
    path.write_bytes(b'{"summary":"' + b"x" * 1_048_576 + b'"}')
    result, code = _post(tmp_path, "start", {
        "journey_id": "journey-1", "goal": "Explain the failure",
        "created_at": "2026-08-12T12:00:00Z", "intake_ref": "intake.json",
    })
    assert code == 422 and result["error"]["code"] == "INVALID_ARTIFACT"
    assert "traceback" not in json.dumps(result).lower()


@pytest.mark.parametrize("raw,expected", [
    (b'{"journey_ref":"a","journey_ref":"b","lens":"Rescue"}', "INVALID_JSON"),
    (b'{"journey_ref":"a","lens":NaN}', "INVALID_JSON"),
    (b'[]', "INVALID_REQUEST"),
    (b'{', "INVALID_JSON"),
])
def test_route_rejects_malformed_duplicate_and_nonfinite_json(raw, expected, tmp_path):
    body, code = evidence_post("/api/evidence/project", raw, root=tmp_path)
    assert code == 400 and body["error"]["code"] == expected
    assert body["schema"] == "flywheel.evidence-transport-error/v1"
    assert "traceback" not in json.dumps(body).lower() and str(tmp_path) not in json.dumps(body)


@pytest.mark.parametrize("body,code_name", [
    ({"lens": "Rescue"}, "MISSING_FIELD"),
    ({"journey_ref": "../outside.json", "lens": "Rescue"}, "INVALID_REF"),
    ({"journey_ref": "C:/private/journey.json", "lens": "Rescue"}, "INVALID_REF"),
    ({"journey_ref": "missing.json", "lens": "Rescue"}, "MISSING_REF"),
])
def test_route_rejects_missing_or_unsafe_refs_without_host_details(tmp_path, body, code_name):
    result, code = _post(tmp_path, "project", body)
    assert 400 <= code < 500 and result["error"]["code"] == code_name
    assert str(tmp_path) not in json.dumps(result)


def test_route_rejects_unsupported_lens_as_typed_422(tmp_path):
    _write_json(tmp_path / "journey.json", _journey())
    result, code = _post(tmp_path, "project", {
        "journey_ref": "journey.json", "lens": "Score",
    })
    assert code == 422 and result["error"]["code"] == "UNSUPPORTED_LENS"
    assert "traceback" not in json.dumps(result).lower()


def test_check_preserves_code_containment_refusal_before_candidate_access(tmp_path, monkeypatch):
    _write_json(tmp_path / "journey.json", _journey())
    _write_json(tmp_path / "context.json", _context("does-not-exist.py"))
    monkeypatch.setattr("harness.evidence_packet._snap",
                        lambda *a, **k: pytest.fail("candidate bytes were read"))
    monkeypatch.setattr(socket, "create_connection",
                        lambda *a, **k: pytest.fail("network was called"))
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *a, **k: pytest.fail("network was called"))
    result, code = _post(tmp_path, "check", {
        "journey_ref": "journey.json", "claim_id": "claim-root",
        "oracle_id": "code", "candidate_ref": "does-not-exist.py",
        "context_ref": "context.json",
    })
    assert code == 422 and result["verdict"] == "UNVERIFIABLE"
    assert result["unverifiable_reason"] == "EXECUTION_CONTAINMENT_UNAVAILABLE"
    assert result["oracle_calls_consumed"] == 0 and "receipt_ref" not in result
    assert not (tmp_path / "receipts").exists()


def test_unregistered_oracle_is_typed_422_without_candidate_access(tmp_path, monkeypatch):
    _write_json(tmp_path / "journey.json", _journey())
    _write_json(tmp_path / "context.json", _context("missing.py"))
    monkeypatch.setattr("harness.evidence_packet._snap",
                        lambda *a, **k: pytest.fail("candidate bytes were read"))
    result, code = _post(tmp_path, "check", {
        "journey_ref": "journey.json", "claim_id": "claim-root",
        "oracle_id": "unregistered", "candidate_ref": "missing.py",
        "context_ref": "context.json",
    })
    assert code == 422 and result["verdict"] == "UNVERIFIABLE"
    assert result["unverifiable_reason"] == "ORACLE_UNAVAILABLE"
    assert str(tmp_path) not in json.dumps(result)


def test_routes_never_enter_provider_endpoint_or_model_dispatch(tmp_path, monkeypatch):
    _write_json(tmp_path / "journey.json", _journey())
    _write_json(tmp_path / "context.json", _context("missing.py"))
    def forbidden(*args, **kwargs):
        pytest.fail("external dispatcher was invoked")
    monkeypatch.setattr("harness.providers.make_proposer", forbidden)
    monkeypatch.setattr("harness.endpoint_registry.make_endpoint_proposer", forbidden)
    monkeypatch.setattr("harness.model_router.route_role", forbidden)
    request = {"journey_ref": "journey.json", "claim_id": "claim-root",
        "oracle_id": "code", "candidate_ref": "missing.py",
        "context_ref": "context.json"}
    result, code = _post(tmp_path, "check", request)
    assert code == 422 and result["unverifiable_reason"] == "EXECUTION_CONTAINMENT_UNAVAILABLE"


def _checked_measurement(root):
    journey = _journey()
    candidate = root / "measurement.json"
    _write_json(candidate, {"effect": 0.1, "ci_low": 0.05, "ci_high": 0.15,
        "min_effect": 0.2, "n": 10,
        "negative_control": {"effect": 0, "ci_low": -0.1, "ci_high": 0.1}})
    context = {"task_id": "transport-v1", "prompt": "Check measurement",
        "oracle_cmd": "measurement-gate", "candidate_ref": candidate.name,
        "raw_artifact_refs": [candidate.name], "timeout_seconds": 5}
    check = run_journey_check(journey, "claim-root", "ml", candidate, context)
    claim = {**journey["events"][-1]["claims"][0], "verdict": check["verdict"],
             "receipt_refs": [check["receipt_ref"]],
             "raw_artifact_refs": check["raw_artifact_refs"]}
    return append_event(journey, {"stage": "preflight",
        "occurred_at": "2026-08-12T12:02:00Z", "claims": [claim]})


def test_export_and_anchored_recheck_use_relative_packet_ref(tmp_path):
    _write_json(tmp_path / "journey.json", _checked_measurement(tmp_path))
    exported, code = _post(tmp_path, "export", {
        "journey_ref": "journey.json", "packet_ref": "packets/journey-1",
    })
    assert code == 200 and exported["structural_verdict"] == "MATCH"
    checked, code = _post(tmp_path, "recheck", {
        "packet_ref": "packets/journey-1",
        "expected_manifest_sha256": exported["packet_sha256"],
    })
    assert code == 200 and checked["verdict"] == "MATCH"
    assert str(tmp_path) not in json.dumps([exported, checked])


class _Headers:
    def __init__(self, size): self.size = size
    def get(self, key, default=None):
        return self.size if key == "Content-Length" else default


def test_gateway_dispatch_preserves_strict_duplicate_key_rejection(tmp_path):
    raw = b'{"journey_ref":"a","journey_ref":"b","lens":"Rescue"}'
    handler = gateway._Handler.__new__(gateway._Handler)
    handler.path, handler.root = "/api/evidence/project", tmp_path
    handler.headers, handler.rfile = _Headers(str(len(raw))), io.BytesIO(raw)
    sent = {}
    handler._json = lambda body, code=200: sent.update(body=body, code=code)
    handler._post()
    assert sent["code"] == 400 and sent["body"]["error"]["code"] == "INVALID_JSON"


@pytest.mark.parametrize("action", ["start", "project", "check", "export", "recheck"])
def test_gateway_exposes_each_evidence_post_route(action, tmp_path, monkeypatch):
    raw = b"{}"
    handler = gateway._Handler.__new__(gateway._Handler)
    handler.path, handler.root = f"/api/evidence/{action}", tmp_path
    handler.headers, handler.rfile = _Headers(str(len(raw))), io.BytesIO(raw)
    sent, seen = {}, []
    monkeypatch.setattr("harness.evidence_route.evidence_post",
        lambda path, body, root: (seen.append((path, body, root)) or
                                  ({"schema": "route-witness/v1", "action": action}, 209)))
    handler._json = lambda body, code=200: sent.update(body=body, code=code)
    handler._post()
    assert sent == {"body": {"schema": "route-witness/v1", "action": action}, "code": 209}
    assert seen == [(f"/api/evidence/{action}", raw, tmp_path)]

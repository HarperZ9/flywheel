import json

import pytest

from harness.evidence_route import evidence_post


def _start(tmp_path, intake):
    (tmp_path / "intake.json").write_text(json.dumps(intake), encoding="utf-8")
    return evidence_post("/api/evidence/start", json.dumps({
        "journey_id": "journey-uri-security", "goal": "Explain the failure",
        "created_at": "2026-08-12T12:00:00Z", "intake_ref": "intake.json",
    }), root=tmp_path)


@pytest.mark.parametrize("uri", [
    "FiLe:%2Fhome%2Fprivate%2Finput.json",
    "fIlE:%5C%5Cserver%5Cprivate%5Cinput.json",
    "FILE:C%3A%5CUsers%5Cprivate%5Cinput.json",
    "file:relative/path",
])
@pytest.mark.parametrize("location", ["key", "value"])
def test_file_uri_is_rejected_without_echo_for_keys_and_values(tmp_path, uri, location):
    intake = {uri: "bounded"} if location == "key" else {"source": uri}
    result, status = _start(tmp_path, intake)
    assert status == 422
    assert result == {"schema": "flywheel.evidence-transport-error/v1", "error": {
        "code": "UNSAFE_METADATA", "message": "metadata contains an unsafe reference"}}
    assert uri not in json.dumps(result)


@pytest.mark.parametrize("name", [
    "access_token", "refresh_token", "token", "X-Amz-Credential",
    "provider-api-key", "client_secret",
])
@pytest.mark.parametrize("component", ["query", "fragment"])
@pytest.mark.parametrize("location", ["key", "value"])
def test_https_secret_parameter_name_is_rejected_without_echo(
        tmp_path, name, component, location):
    separator = "?" if component == "query" else "#"
    url = f"https://example.com/public{separator}{name}=opaque"
    intake = {url: "bounded"} if location == "key" else {"source_url": url}
    result, status = _start(tmp_path, intake)
    assert status == 422
    assert result == {"schema": "flywheel.evidence-transport-error/v1", "error": {
        "code": "UNSAFE_METADATA", "message": "metadata contains a secret-bearing field"}}
    assert url not in json.dumps(result)

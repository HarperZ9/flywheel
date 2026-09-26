"""F-20: the scaffold route, moved into trace_routes, keeps bearer auth."""
import json
import urllib.error
import urllib.request

import pytest

from capture_channel_fixture import running_gateway


def _post(port, body, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(f"http://127.0.0.1:{port}/api/scaffold",
                                     data=json.dumps(body).encode(), headers=headers,
                                     method="POST")
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status, json.loads(response.read())


def test_without_credentials_is_401(tmp_path, monkeypatch):
    with running_gateway(tmp_path, monkeypatch) as server:
        with pytest.raises(urllib.error.HTTPError) as refused:
            _post(server.server_address[1], {"prompt": "p", "answer": "a"})
    assert refused.value.code == 401


def test_with_the_bearer_token_is_200_and_chains_a_receipt(tmp_path, monkeypatch):
    with running_gateway(tmp_path, monkeypatch) as server:
        token = (tmp_path / "gateway.token").read_text().strip()
        status, doc = _post(server.server_address[1],
                            {"prompt": "no links here", "answer": "done"}, token)
    assert status == 200
    assert doc["schema"] == "flywheel.turn-receipt/v1"
    assert len(doc["eid"]) == 24 and len(doc["chain_hash"]) == 64


def test_an_empty_body_is_refused(tmp_path, monkeypatch):
    with running_gateway(tmp_path, monkeypatch) as server:
        token = (tmp_path / "gateway.token").read_text().strip()
        with pytest.raises(urllib.error.HTTPError) as refused:
            _post(server.server_address[1], {}, token)
    assert refused.value.code == 400

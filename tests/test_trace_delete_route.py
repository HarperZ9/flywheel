"""I12, I17 on the deletion routes: bearer authentication, no path or owner
from the body, and no apply without presence bound to the plan digest."""
import json
import urllib.error
import urllib.request

import pytest

from capture_channel_fixture import running_gateway
from delete_fixtures import OWNER, plant_trace
from trace_enc_fakes import StreamTestProvider, using


def _post(port, path, body, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}",
                                     data=json.dumps(body).encode(), headers=headers,
                                     method="POST")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


@pytest.fixture
def gateway(tmp_path, monkeypatch):
    (tmp_path / "owner.ref").write_text(OWNER)
    with using(StreamTestProvider()), running_gateway(tmp_path, monkeypatch) as server:
        token = (tmp_path / "gateway.token").read_text().strip()
        yield tmp_path, server.server_address[1], token


def test_planning_needs_the_bearer_token(gateway):
    home, port, _ = gateway
    ref = plant_trace(home)
    assert _post(port, "/api/traces/delete/plan", {"trace_refs": [ref]})[0] == 401


@pytest.mark.parametrize("extra", [{"path": "C:/x"}, {"owner_ref": OWNER},
                                   {"root": "../state"}])
def test_a_path_or_owner_in_the_body_is_422(gateway, extra):
    home, port, token = gateway
    ref = plant_trace(home)
    status, _ = _post(port, "/api/traces/delete/plan", {"trace_refs": [ref], **extra}, token)
    assert status == 422


def test_a_malformed_ref_is_422(gateway):
    _, port, token = gateway
    status, _ = _post(port, "/api/traces/delete/plan", {"trace_refs": ["../../x"]}, token)
    assert status == 422


def test_apply_without_presence_is_refused_then_with_it_deletes(gateway):
    home, port, token = gateway
    ref = plant_trace(home)
    status, plan = _post(port, "/api/traces/delete/plan", {"trace_refs": [ref]}, token)
    assert status == 200 and "C:" not in json.dumps(plan) and str(home) not in json.dumps(plan)
    status, refused = _post(port, "/api/traces/delete/apply",
                            {"plan_digest": plan["plan_digest"]}, token)
    assert status == 403 and refused["error"]["code"] == "PRESENCE_REQUIRED"
    _, presence = _post(port, "/api/traces/presence",
                        {"kind": "delete_apply", "plan_digest": plan["plan_digest"]}, token)
    status, report = _post(port, "/api/traces/delete/apply",
                           {"plan_digest": plan["plan_digest"],
                            "presence_ref": presence["ref"]}, token)
    assert status == 200 and report["state"] == "DELETED" and report["presence"] == "none"

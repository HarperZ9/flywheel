"""I12 and I17 on the presence routes: bearer authentication, no owner and
no path from the body, and the method in effect in every response."""
import json
import urllib.error
import urllib.request

import pytest

from capture_channel_fixture import running_gateway

DIGEST = "a" * 64


def _post(port, path, body, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}",
                                     data=json.dumps(body).encode(), headers=headers,
                                     method="POST")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


@pytest.fixture
def gateway(tmp_path, monkeypatch):
    with running_gateway(tmp_path, monkeypatch) as server:
        yield server.server_address[1], (tmp_path / "gateway.token").read_text().strip()


def test_a_challenge_needs_the_bearer_token(gateway):
    port, _ = gateway
    status, _ = _post(port, "/api/traces/presence", {"kind": "export", "plan_digest": DIGEST})
    assert status == 401


def test_a_challenge_is_confirmed_with_the_method_in_effect(gateway):
    from harness.trace_presence import method_digest
    port, token = gateway
    status, body = _post(port, "/api/traces/presence",
                         {"kind": "presence_method",
                          "plan_digest": method_digest("windows-hello")}, token)
    assert status == 200
    assert body["ref"].startswith("prs_") and body["method"] == "none"
    assert body["summary"] == "Change the presence method to windows-hello."
    assert "agents included" in body["presence_statement"]


def test_a_digest_the_gateway_cannot_describe_is_refused(gateway):
    """The prompt text comes from the plan or grant behind the digest; a
    digest with nothing behind it would be a bare prefix, so it is refused."""
    port, token = gateway
    status, body = _post(port, "/api/traces/presence",
                         {"kind": "export", "plan_digest": DIGEST}, token)
    assert status == 404 and body["error"]["code"] == "PRESENCE_UNDESCRIBED"


def test_there_is_no_approval_route(gateway):
    port, token = gateway
    status, _ = _post(port, "/api/traces/presence/approve", {"ref": "prs_" + "0" * 32}, token)
    assert status == 404


@pytest.mark.parametrize("extra", [{"owner_ref": "owner_" + "b" * 32},
                                   {"path": "C:/x"}, {"destination": "../out"},
                                   {"note": "\\\\server\\share"}])
def test_an_owner_or_a_path_in_the_body_is_422(gateway, extra):
    port, token = gateway
    status, _ = _post(port, "/api/traces/presence",
                      {"kind": "export", "plan_digest": DIGEST, **extra}, token)
    assert status == 422


def test_an_unknown_kind_or_a_malformed_digest_is_422(gateway):
    port, token = gateway
    assert _post(port, "/api/traces/presence", {"kind": "format_disk",
                                                "plan_digest": DIGEST}, token)[0] == 422
    assert _post(port, "/api/traces/presence", {"kind": "export",
                                                "plan_digest": "short"}, token)[0] == 422

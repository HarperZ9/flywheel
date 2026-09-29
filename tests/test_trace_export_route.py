"""I12, I17 on the export route: bearer authentication, no path from the
body, a destination only through a one-use grant the CLI wrote, and presence
bound to the export digest."""
import pytest

from capture_channel_fixture import running_gateway
from delete_fixtures import OWNER, plant_trace
from harness.trace_export_dest import create_grant
from harness.trace_export_verify import verify
from harness.trace_presence import confirm
from test_trace_delete_route import _post
from trace_enc_fakes import StreamTestProvider, using


@pytest.fixture
def gateway(tmp_path, monkeypatch):
    from harness import trace_witness
    home = tmp_path / "home"
    home.mkdir()
    (home / "owner.ref").write_text(OWNER)
    monkeypatch.setattr(trace_witness, "default_sink", trace_witness.MemorySink)
    with using(StreamTestProvider()), running_gateway(home, monkeypatch) as server:
        token = (home / "gateway.token").read_text().strip()
        plant_trace(home)
        yield home, server.server_address[1], token, tmp_path / "out"


def test_the_route_needs_the_bearer_token(gateway):
    _, port, _, _ = gateway
    assert _post(port, "/api/traces/export", {"grant_ref": "xgr_" + "0" * 32})[0] == 401


@pytest.mark.parametrize("extra", [{"out": "C:/x"}, {"destination": "/tmp/x"},
                                   {"owner_ref": OWNER}])
def test_a_path_or_owner_in_the_body_is_422(gateway, extra):
    _, port, token, _ = gateway
    status, _ = _post(port, "/api/traces/export", {"grant_ref": "xgr_" + "0" * 32, **extra},
                      token)
    assert status == 422


def test_an_export_through_a_grant_with_presence(gateway):
    home, port, token, out = gateway
    grant = create_grant(home, OWNER, out, {})
    status, body = _post(port, "/api/traces/export", {"grant_ref": grant["grant_ref"],
                                                      "presence_ref": "prs_" + "0" * 32}, token)
    assert status == 403 and not out.exists()
    grant = create_grant(home, OWNER, out, {})
    ref = confirm(home / "state", OWNER, "export", grant["export_digest"], "export")
    status, body = _post(port, "/api/traces/export", {"grant_ref": grant["grant_ref"],
                                                      "presence_ref": ref}, token)
    assert status == 200 and body["state"] == "EXPORTED", body
    assert verify(out) == ("MATCH", [])
    status, _ = _post(port, "/api/traces/export", {"grant_ref": grant["grant_ref"],
                                                   "presence_ref": ref}, token)
    assert status == 404

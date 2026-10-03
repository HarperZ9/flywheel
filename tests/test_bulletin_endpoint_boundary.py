"""Default client operations cannot spend a publisher's remote backend."""
# asyncio first: on Windows, asyncio.windows_utils subclasses subprocess.Popen at
# import time. The fixture below replaces Popen with a function, so a first
# import of asyncio under that patch half-initializes the package and breaks
# every later test in the same process.
import asyncio  # noqa: F401
import json
import subprocess
import urllib.request

import pytest

from harness import lanes
from harness.lane_call_route import handle_lane_call
from harness.lane_probe_cache import ProbeCache, probe_lanes
from harness.lane_roster_row import roster_rows
from harness.lane_setup import SetupChecks


@pytest.fixture(params=[False, True], ids=["source", "frozen"])
def runtime(request, monkeypatch, tmp_path):
    monkeypatch.delenv("FLYWHEEL_BULLETIN_URL", raising=False)
    monkeypatch.setattr(lanes, "_frozen", lambda: request.param)
    monkeypatch.setattr(lanes, "resolve_source_repo", lambda lane: None)
    monkeypatch.setattr(lanes, "_installed_version", lambda lane: None)
    monkeypatch.setattr(lanes, "_importable", lambda module: False)
    monkeypatch.setattr(lanes, "read_registry", lambda: {})
    # Other default lanes cannot start processes during this boundary test.
    def no_process(*args, **kwargs):
        raise FileNotFoundError("fixture has no local lane programs")
    monkeypatch.setattr(subprocess, "Popen", no_process)
    return ProbeCache(tmp_path / "probes.json", engine="test")


def test_default_roster_probe_and_call_need_endpoint_without_network(runtime, monkeypatch):
    attempted = []
    def deny_urlopen(*args, **kwargs):
        attempted.append(args)
        raise AssertionError("default client attempted a remote request")
    monkeypatch.setattr(urllib.request, "urlopen", deny_urlopen)
    rows = probe_lanes(lanes.LANES, cache=runtime)
    assert set(rows) == set(lanes.LANES)
    row = rows["bulletin"]
    assert row["blocking_codes"] == ["http_endpoint_unset"]
    card = roster_rows([row], probed=True, cache=runtime, checks=SetupChecks(environ={}))[0]
    assert card["state"] == "needs_setup"
    assert "FLYWHEEL_BULLETIN_URL" in str(card)
    result, status = handle_lane_call("/api/lane/bulletin/board_rooms", {})
    assert (status, result["code"], result["reason"], result["setup"]) == (
        409, "LANE_SETUP_REQUIRED", "http_endpoint_unset", ["http_endpoint"])
    assert attempted == []


class Response:
    status = 200
    headers = {"content-type": "application/json"}
    def __init__(self, body):
        self.body = body
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self):
        return json.dumps(self.body).encode() if self.body else b""


def test_owner_selected_https_endpoint_still_probes_and_calls(runtime, monkeypatch):
    monkeypatch.setenv("FLYWHEEL_BULLETIN_URL", "https://operator.example/mcp")
    methods = []
    def serve(req, **kwargs):
        assert req.full_url == "https://operator.example/mcp"
        msg = json.loads(req.data)
        methods.append(msg["method"])
        if "id" not in msg:
            return Response(None)
        results = {
            "initialize": {"protocolVersion": "2025-06-18", "capabilities": {},
                           "serverInfo": {"name": "bulletin", "version": "0.5.0"}},
            "tools/list": {"tools": [{"name": "bulletin_status"}, {"name": "board_rooms"}]},
            "tools/call": {"content": [{"type": "text", "text": '{"ok":true}'}]},
        }
        return Response({"jsonrpc": "2.0", "id": msg["id"], "result": results[msg["method"]]})
    monkeypatch.setattr(urllib.request, "urlopen", serve)
    assert lanes.lane_status("bulletin", probe=True)["status"] == "live"
    result, status = handle_lane_call("/api/lane/bulletin/board_rooms", {})
    assert (status, result) == (200, {"ok": True})
    assert methods.count("initialize") == 2 and methods.count("tools/call") == 2


def test_confirmed_registration_without_endpoint_stays_local(monkeypatch, tmp_path):
    from harness.bulletin_identity_route import bulletin_identity_register_post
    monkeypatch.delenv("FLYWHEEL_BULLETIN_BASE_URL", raising=False)
    def denied(**kwargs):
        pytest.fail("identity preparation must not start before endpoint selection")
    body, status = bulletin_identity_register_post(
        {"schema": "flywheel.bulletin-identity-register-request/v1",
         "action": "register", "confirm_register": True}, tmp_path,
        prepare=denied, keychain_available_fn=lambda: True,
        signing_available_fn=lambda: True)
    assert status == 400 and body["error"]["code"] == "BASE_URL_UNAVAILABLE"


def test_identity_cli_without_endpoint_refuses_before_key_or_network(monkeypatch, capsys):
    from harness.bulletin_identity_cli import main
    monkeypatch.delenv("FLYWHEEL_BULLETIN_BASE_URL", raising=False)
    assert main(["prepare", "--register"]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "BASE_URL_UNAVAILABLE"


@pytest.mark.parametrize("origin, expected", [
    ("https://operator.example:443", "https://operator.example"),
    ("https://operator.example:8443", "https://operator.example:8443"),
    ("https://[2001:0db8:0:0:0:0:0:1]:443", "https://[2001:db8::1]"),
])
def test_configured_identity_origin_uses_canonical_comparison(monkeypatch, origin, expected):
    from harness.bulletin_identity_origin import validate_bulletin_base_url
    monkeypatch.setenv("FLYWHEEL_BULLETIN_BASE_URL", origin)
    assert validate_bulletin_base_url() == expected


def test_identity_status_does_not_offer_registration_without_endpoint(monkeypatch):
    from harness.bulletin_identity_route import bulletin_identity_get
    monkeypatch.delenv("FLYWHEEL_BULLETIN_BASE_URL", raising=False)
    body, status = bulletin_identity_get(credential_source=lambda name: "keychain",
        keychain_available_fn=lambda: True, signing_available_fn=lambda: True)
    assert status == 200 and body["register_available"] is False
    assert body["unavailable_reason"] == "BASE_URL_UNAVAILABLE"


def test_outcome_preview_without_selected_origin_refuses(monkeypatch):
    # A public post preview names its destination, and a later grant approves
    # that exact destination. A build default would make the publisher's own
    # board the target for anyone who never chose one.
    from harness.outcome_bulletin import OutcomeBulletinError, build_preview
    from tests.test_outcome_bulletin import INDEX_OUTCOME
    monkeypatch.delenv("FLYWHEEL_BULLETIN_BASE_URL", raising=False)
    with pytest.raises(OutcomeBulletinError) as caught:
        build_preview(dict(INDEX_OUTCOME))
    assert caught.value.code == "BULLETIN_ORIGIN_UNSET"


def test_outcome_preview_ignores_ambient_origin_and_uses_the_explicit_one(monkeypatch):
    from harness.outcome_bulletin import OutcomeBulletinError, build_preview
    from tests.test_outcome_bulletin import INDEX_OUTCOME
    monkeypatch.setenv("FLYWHEEL_BULLETIN_BASE_URL", "https://ambient.example")
    with pytest.raises(OutcomeBulletinError):
        build_preview(dict(INDEX_OUTCOME))
    preview = build_preview(dict(INDEX_OUTCOME),
                            bulletin_base_url="https://operator.example:443")
    assert preview["target"]["bulletin_base_url"] == "https://operator.example"


def test_outcome_cli_targets_the_configured_origin(monkeypatch, tmp_path, capsys):
    from harness.outcome_bulletin_cli import main
    from tests.test_outcome_bulletin import INDEX_OUTCOME
    monkeypatch.setenv("FLYWHEEL_BULLETIN_BASE_URL", "https://operator.example")
    source = tmp_path / "outcome.json"
    source.write_text(json.dumps(INDEX_OUTCOME), encoding="utf-8")
    assert main(["preview", "--outcome", str(source)]) == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview["target"]["bulletin_base_url"] == "https://operator.example"


def test_outcome_cli_without_selected_origin_refuses(monkeypatch, tmp_path, capsys):
    from harness.outcome_bulletin_cli import main
    from tests.test_outcome_bulletin import INDEX_OUTCOME
    monkeypatch.delenv("FLYWHEEL_BULLETIN_BASE_URL", raising=False)
    source = tmp_path / "outcome.json"
    source.write_text(json.dumps(INDEX_OUTCOME), encoding="utf-8")
    assert main(["preview", "--outcome", str(source)]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "BULLETIN_ORIGIN_UNSET"

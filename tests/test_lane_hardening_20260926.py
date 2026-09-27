"""Hardening from the 2026-09-26 finish security review (F9).

- A lane id may not be a Windows device name (CON, NUL, COM1 ...), which a lane
  that joins the id into ``<id>.json`` would open as a device.
- Key-shaped names cover ``*_AUTH``, ``*_BEARER``, ``*_COOKIE``, ``*_DSN`` and
  ``*_PASSPHRASE``, and a lane-declared value that carries ``user:token@`` in a
  URL is dropped from the child.
- ``POST /api/lanes/install`` is private and takes an exact ``lane.install``
  grant; a bearer token alone installs nothing. It installs the pinned version.
"""
from __future__ import annotations

import pytest

from harness.gateway_custody import is_private
from harness.gateway_operation import action_for_path, canonicalize_operation
from harness.lane_credentials import key_shaped
from harness.lane_tier_gate import argument_refusal

REFS = {"data_refs": [], "credential_refs": []}


@pytest.mark.parametrize("value", ["CON", "nul", "Aux", "PRN", "COM1", "com9", "LPT1",
                                   "lpt9", "CON.json", "nul.txt"])
def test_a_windows_device_name_is_not_a_plain_id(value, tmp_path, monkeypatch):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path / "home"))
    refused = argument_refusal("learn", "learn_tutor_mastery", {"sessionId": value})
    assert refused and refused["reason"] == "argument_refused", value


@pytest.mark.parametrize("value", ["console", "com10", "nullable", "lpt", "algebra-1"])
def test_names_that_only_look_like_devices_stay_plain(value, tmp_path, monkeypatch):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path / "home"))
    assert argument_refusal("learn", "learn_tutor_mastery", {"sessionId": value}) is None


@pytest.mark.parametrize("name", ["SERVICE_AUTH", "HF_BEARER", "SESSION_COOKIE",
                                  "SENTRY_DSN", "GPG_PASSPHRASE", "OPENAI_API_KEY"])
def test_more_credential_names_are_key_shaped(name):
    assert key_shaped(name)


@pytest.mark.parametrize("name", ["AUTHOR", "AUTH_MODE_LABEL", "DSN_HOST", "BASE_URL"])
def test_ordinary_names_stay_plain(name):
    assert not key_shaped(name)


def test_a_declared_url_with_userinfo_is_dropped():
    from harness.lane_env import lane_child_environment
    declared = ("GLM_CLOUD_BASE_URL", "GLM_MODEL")
    env = lane_child_environment(
        {"GLM_CLOUD_BASE_URL": "https://user:tok3n@api.example.invalid/v1",
         "GLM_MODEL": "glm-4", "PATH": "C:/Windows"}, declared, ())
    assert "GLM_CLOUD_BASE_URL" not in env and env["GLM_MODEL"] == "glm-4"
    plain = lane_child_environment(
        {"GLM_CLOUD_BASE_URL": "https://api.example.invalid/v1"}, declared, ())
    assert plain["GLM_CLOUD_BASE_URL"] == "https://api.example.invalid/v1"


def test_a_granted_url_with_userinfo_is_the_operator_choice():
    from harness.lane_env import lane_child_environment
    env = lane_child_environment({"HTTPS_PROXY": "http://me:pw@proxy.invalid:8080"},
                                 (), ("HTTPS_PROXY",))
    assert env["HTTPS_PROXY"] == "http://me:pw@proxy.invalid:8080"


def test_the_install_route_is_a_private_granted_action():
    assert is_private("/api/lanes/install")
    assert action_for_path("/api/lanes/install") == "lane.install"
    operation = canonicalize_operation("lane.install", {**REFS, "name": "gather"})
    assert operation.scopes == ("write", "exec", "network")
    assert dict(operation.destination) == {"kind": "setting", "ref": "lane-install"}


def test_an_ungranted_install_post_installs_nothing(tmp_path, monkeypatch):
    import harness.lanes as lanes
    from tests.test_lane_console_route import _post, _start
    ran = []
    monkeypatch.setattr(lanes, "install_lane", lambda *a, **k: ran.append(a) or {})
    server, _home, _owner, token = _start(tmp_path, monkeypatch)
    try:
        status, _body = _post(server, token, "/api/lanes/install", {"name": "gather"})
    finally:
        server.shutdown()
        server.server_close()
    assert status in (403, 422) and ran == []


def _install_after_grant(body: dict) -> dict:
    """What POST /api/lanes/install does once the gateway consumed its lane.install
    grant: the approved operation is the request body."""
    from harness import gateway
    from harness.lane_console_route import _install
    handler = gateway._Handler.__new__(gateway._Handler)
    handler._gateway_operation = body
    sent = {}
    handler._json = lambda payload, code=200: sent.update(body=payload, code=code)
    _install(handler)
    return sent


def test_a_granted_install_still_requires_a_name():
    sent = _install_after_grant({**REFS})
    assert sent["code"] == 400 and "name" in sent["body"]["error"]


def test_a_granted_install_reports_an_unknown_lane_honestly():
    sent = _install_after_grant({**REFS, "name": "no-such-lane"})
    assert sent["code"] == 200 and sent["body"]["installed"] is False
    assert "unknown lane" in sent["body"]["detail"]


def test_a_granted_install_of_a_bundled_lane_is_a_noop():
    sent = _install_after_grant({**REFS, "name": "local-model"})
    assert sent["code"] == 200 and sent["body"]["installed"] is True
    assert "bundled" in sent["body"]["detail"]

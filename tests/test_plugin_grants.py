import pytest
import io
import json
import os
import subprocess

from harness import gateway, marketplace, plugins
from harness.gateway_actions import (
    GatewayDispatchError, dispatch_authorized, dispatch_builtin,
)
from harness.gateway_grant_route import gateway_grant_post
from harness.gateway_operation import AuthorizedOperation
from harness.journey_store import JourneyStore, MutationCommand
from harness.mcp_client import LaunchSpec, StdioTransport


NOW = "2026-08-15T12:00:00Z"
OWNER = "owner_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
JOURNEY = "jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def _operation(action, body):
    return AuthorizedOperation.for_test(
        action=action, operation=body,
        scopes={
            "plugin.probe": ("exec", "network", "plugin"),
            "plugin.call": ("write", "exec", "network", "plugin"),
            "plugin.register": ("write", "plugin"),
            "plugin.toggle": ("write", "plugin"),
            "plugin.remove": ("write", "plugin"),
        }[action])


@pytest.mark.parametrize("action", [
    "plugin.probe", "plugin.call", "plugin.register",
    "plugin.toggle", "plugin.remove",
])
def test_plugin_dispatch_invokes_only_the_exact_selected_adapter(action):
    calls = []
    handlers = {name: (lambda op, name=name: calls.append(
        (name, dict(op.operation))) or {"ok": name}) for name in [
            "plugin.probe", "plugin.call", "plugin.register",
            "plugin.toggle", "plugin.remove"]}
    result = dispatch_authorized(_operation(action, {"name": "bounded"}),
                                 handlers)
    assert result == {"ok": action}
    assert calls == [(action, {"name": "bounded"})]


def test_missing_or_wrong_adapter_cannot_fall_through_to_plugin_start():
    calls = []
    operation = _operation("plugin.probe", {"name": "bounded"})
    with pytest.raises(GatewayDispatchError) as failure:
        dispatch_authorized(operation, {"plugin.call": lambda _: calls.append(1)})
    assert failure.value.code == "INVALID_REQUEST"
    assert calls == []


def test_plugin_failure_is_fixed_and_never_echoes_exception():
    def fail(_):
        raise OSError("C:/private/secret")
    with pytest.raises(GatewayDispatchError) as failure:
        dispatch_authorized(_operation("plugin.call", {
            "name": "bounded", "tool": "run", "arguments": {},
            "credential_refs": []}), {"plugin.call": fail})
    assert failure.value.code == "EXTERNAL_ACTION_FAILED"
    assert "private" not in str(failure.value)


def test_gateway_probe_adapter_removes_internal_stderr(monkeypatch):
    monkeypatch.setattr(plugins, "probe_plugin", lambda _name, **_kwargs: {
        "name": "bounded", "kind": "lane", "status": "unreachable",
        "detail": "server stderr: C:/private/secret",
    })
    result, status = dispatch_builtin(
        _operation("plugin.probe", {"name": "bounded"}))
    assert status == 200
    assert result == {"name": "bounded", "kind": "lane",
                      "status": "unreachable",
                      "detail": "plugin probe is unavailable"}


def _handler(tmp_path, body):
    raw, sent = json.dumps(body).encode(), {}
    handler = gateway._Handler.__new__(gateway._Handler)
    handler.path, handler.owner_ref = "/api/plugins/probe", OWNER
    handler.flywheel_home, handler.clock = tmp_path, lambda: NOW
    handler.headers = type("Headers", (), {"get": lambda _, key, default=None:
        str(len(raw)) if key == "Content-Length" else default})()
    handler.rfile = io.BytesIO(raw)
    handler._json = lambda value, code=200: sent.update(body=value, code=code)
    handler._post()
    return sent


def test_gateway_plugin_route_dispatches_only_after_exact_one_use_grant(
        tmp_path, monkeypatch):
    head = JourneyStore(tmp_path / "state").create(MutationCommand(
        OWNER, JOURNEY, None, "create-1", "intake",
        {"legacy_label": None, "goal": "plugin", "intake": {},
         "occurred_at": NOW})).event_head_sha256
    prepare = {"schema": "flywheel.gateway-operation/v1",
               "journey_ref": JOURNEY, "expected_event_head": head,
               "client_request_id": "request-1",
               "operation": {"name": "gather", "data_refs": [],
                             "credential_refs": []}}
    proposal, _ = gateway_grant_post(
        "/api/gateway-grants/prepare/plugin.probe", json.dumps(prepare).encode(),
        owner_ref=OWNER, state_root=tmp_path / "state", clock=lambda: NOW)
    approval, _ = gateway_grant_post(
        "/api/gateway-grants/approve-once",
        json.dumps({"proposal_ref": proposal["proposal_ref"]}).encode(),
        owner_ref=OWNER, state_root=tmp_path / "state", clock=lambda: NOW)
    calls = []
    monkeypatch.setattr(plugins, "probe_plugin", lambda name, **_kwargs:
                        calls.append(name) or {"status": "live"})
    final = {key: prepare[key] for key in prepare if key != "operation"}
    final.update(prepare["operation"]); final["grant_ref"] = approval["grant_ref"]
    assert _handler(tmp_path, final)["code"] == 200
    assert calls == ["gather"]
    assert _handler(tmp_path, final)["code"] == 403
    assert calls == ["gather"]


def test_dispatch_exception_burns_consumed_grant(tmp_path, monkeypatch):
    head = JourneyStore(tmp_path / "state").create(MutationCommand(
        OWNER, JOURNEY, None, "create-1", "intake",
        {"legacy_label": None, "goal": "plugin", "intake": {},
         "occurred_at": NOW})).event_head_sha256
    prepare = {"schema": "flywheel.gateway-operation/v1",
               "journey_ref": JOURNEY, "expected_event_head": head,
               "client_request_id": "request-1",
               "operation": {"name": "gather", "data_refs": [],
                             "credential_refs": []}}
    proposal, _ = gateway_grant_post(
        "/api/gateway-grants/prepare/plugin.probe", json.dumps(prepare).encode(),
        owner_ref=OWNER, state_root=tmp_path / "state", clock=lambda: NOW)
    approval, _ = gateway_grant_post(
        "/api/gateway-grants/approve-once",
        json.dumps({"proposal_ref": proposal["proposal_ref"]}).encode(),
        owner_ref=OWNER, state_root=tmp_path / "state", clock=lambda: NOW)
    calls = []
    monkeypatch.setattr(plugins, "probe_plugin", lambda name, **_kwargs:
                        calls.append(name) or (_ for _ in ()).throw(
                            OSError("C:/private/synthetic-marker")))
    final = {key: prepare[key] for key in prepare if key != "operation"}
    final.update(prepare["operation"]); final["grant_ref"] = approval["grant_ref"]
    failure = _handler(tmp_path, final)
    assert failure["code"] == 502, failure
    assert failure["body"] == {
        "schema": "flywheel.evidence-transport-error/v1",
        "error": {"code": "EXTERNAL_ACTION_FAILED",
                  "message": "authorized external action failed"}}
    assert "synthetic-marker" not in json.dumps(failure)
    assert _handler(tmp_path, final)["code"] == 403
    assert calls == ["gather"]


class _EmptyStream:
    def __iter__(self):
        return iter(())


class _FakeProcess:
    stdin = None
    stdout = _EmptyStream()
    stderr = _EmptyStream()

    def poll(self):
        return None


def test_non_inheriting_launch_spec_passes_only_explicit_environment(monkeypatch):
    marker = "ambient-value-must-not-cross"
    monkeypatch.setenv("CLOUD_ACCESS_TOKEN", marker)
    seen = {}
    monkeypatch.setattr(subprocess, "Popen", lambda argv, **kwargs:
                        seen.update(argv=argv, kwargs=kwargs) or _FakeProcess())

    StdioTransport(LaunchSpec(
        ("bounded-mcp",), env_overrides=(("PATH", "/safe/bin"),),
        inherit_env=False))

    assert seen["kwargs"]["env"] == {"PATH": "/safe/bin"}
    assert marker not in json.dumps(seen)


class _Bindings:
    def child_environment(self, source_env, *, platform):
        assert source_env is os.environ
        assert platform in {"windows", "posix"}
        return {"PATH": "/safe/bin", "GITHUB_TOKEN": "resolved-value"}


def test_registered_plugin_launch_is_non_inheriting_and_explicit(
        monkeypatch, tmp_path):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    ref = "cred_" + "a" * 32
    assert plugins.register_mcp(
        "bounded", ["bounded-mcp"], requires=["GITHUB_TOKEN"],
        credential_refs=[ref])["registered"] == "bounded"
    seen = []

    class FakeClient:
        def __init__(self, launch, **_kwargs):
            seen.append(launch)
        def start(self): return self
        def list_tools(self): return []
        def close(self): pass

    result = plugins.probe_plugin(
        "bounded", client_factory=FakeClient,
        credential_bindings=_Bindings())

    assert result["status"] == "live"
    assert seen == [LaunchSpec(
        ("bounded-mcp",), env_overrides=(
            ("GITHUB_TOKEN", "resolved-value"), ("PATH", "/safe/bin")),
        inherit_env=False)]
    persisted = (tmp_path / "plugins.json").read_text(encoding="utf-8")
    assert "GITHUB_TOKEN" in persisted and ref in persisted
    assert "resolved-value" not in persisted


def test_required_plugin_never_starts_from_ambient_credentials(
        monkeypatch, tmp_path):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    monkeypatch.setenv("GITHUB_TOKEN", "ambient-value-must-not-cross")
    ref = "cred_" + "b" * 32
    plugins.register_mcp("bounded", ["bounded-mcp"],
                         requires=["GITHUB_TOKEN"], credential_refs=[ref])
    calls = []

    result = plugins.call_plugin(
        "bounded", "search", client_factory=lambda *_args, **_kwargs:
        calls.append("constructed"))

    assert result == {"code": "PERMISSION_REQUIRED",
                      "error": "permission required"}
    assert calls == []


def test_added_registry_requirement_refuses_partial_bindings(monkeypatch, tmp_path):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    refs = ["cred_" + "b" * 32, "cred_" + "c" * 32]
    plugins.register_mcp(
        "bounded", ["bounded-mcp"], requires=["TOKEN_A", "TOKEN_B"],
        credential_refs=refs)
    calls = []

    class PartialBindings:
        def child_environment(self, _source, *, platform):
            return {"PATH": "/safe/bin", "TOKEN_A": "one"}

    result = plugins.probe_plugin(
        "bounded", credential_bindings=PartialBindings(),
        client_factory=lambda *_args, **_kwargs: calls.append("constructed"))

    assert result == {"code": "PERMISSION_REQUIRED",
                      "error": "permission required"}
    assert calls == []


def test_marketplace_install_persists_only_slot_names_and_opaque_refs(
        monkeypatch, tmp_path):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    ref = "cred_" + "c" * 32

    result = marketplace.install_from_catalog("github", credential_refs=[ref])

    assert result["registered"] == "github"
    assert plugins.plugin_credentials("github") == (
        ("GITHUB_PERSONAL_ACCESS_TOKEN",), (ref,))
    persisted = json.loads(
        (tmp_path / "plugins.json").read_text(encoding="utf-8"))
    assert persisted["mcp"][0]["requires"] == [
        "GITHUB_PERSONAL_ACCESS_TOKEN"]
    assert persisted["mcp"][0]["credential_refs"] == [ref]


@pytest.mark.parametrize("requires,refs", [
    (["TOKEN"], []),
    ([], ["cred_" + "d" * 32]),
    (["TOKEN"], ["raw-secret"]),
    (["TOKEN", "TOKEN"], ["cred_" + "d" * 32, "cred_" + "e" * 32]),
    (["PATH"], ["cred_" + "d" * 32]),
    (1, []),
    ([], 1),
])
def test_registry_rejects_inexact_credential_metadata(
        monkeypatch, tmp_path, requires, refs):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))

    result = plugins.register_mcp(
        "bounded", ["bounded-mcp"], requires=requires, credential_refs=refs)

    assert result == {"code": "PERMISSION_REQUIRED",
                      "error": "permission required"}
    assert not (tmp_path / "plugins.json").exists()

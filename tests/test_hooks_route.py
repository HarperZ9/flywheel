"""The accountable hooks routes: registry listing, exact-grant
registration, and exact-grant firing. Registration and execution are
separate authorities; the registry persists under the run root; a
failing blocking hook marks the event blocked."""
import json

import pytest

from harness.gateway_custody import is_private
from harness.gateway_grant_route import gateway_grant_post
from harness.hooks_route import handle_hooks_get, handle_hooks_post
from harness.journey_store import JourneyStore, MutationCommand

NOW = "2026-08-24T12:00:00Z"
OWNER = "owner_" + "a" * 32
JOURNEY = "jrn_" + "a" * 32


class _FakeHeaders:
    def __init__(self, n):
        self._n = n

    def get(self, k, d=None):
        return self._n if k == "Content-Length" else d


def _post(path, body):
    import io

    import harness.gateway as gateway
    raw = json.dumps(body).encode()
    h = gateway._Handler.__new__(gateway._Handler)
    h.path = path
    h.headers = _FakeHeaders(str(len(raw)))
    h.rfile = io.BytesIO(raw)
    sent = {}
    h._json = lambda b, code=200: sent.update(body=b, code=code)
    h._post()
    return sent


def _get(path):
    import harness.gateway as gateway
    h = gateway._Handler.__new__(gateway._Handler)
    h.path = path
    h.headers = _FakeHeaders("0")
    sent = {}
    h._json = lambda b, code=200: sent.update(body=b, code=code)
    h._get()
    return sent


ARGS = ["python", "-c", "print('teeth')"]


def _journey(tmp_path):
    state_root = tmp_path / "state"
    event = JourneyStore(state_root).create(MutationCommand(
        OWNER, JOURNEY, None, "genesis", "intake",
        {"legacy_label": None, "goal": "hooks", "intake": {},
         "occurred_at": NOW}))
    return state_root, event.event_head_sha256


def _granted_body(tmp_path, action, operation, *, request_id="request-1",
                  head=None):
    state_root = tmp_path / "state"
    if head is None:
        head = JourneyStore(state_root).load(
            OWNER, JOURNEY)["event_head_sha256"]
    proposal, status = gateway_grant_post(
        f"/api/gateway-grants/prepare/{action}",
        json.dumps({"schema": "flywheel.gateway-operation/v1",
                    "journey_ref": JOURNEY,
                    "expected_event_head": head,
                    "client_request_id": request_id,
                    "operation": {**operation, "data_refs": [],
                                  "credential_refs": []}}).encode(),
        owner_ref=OWNER, state_root=state_root, clock=lambda: NOW)
    assert status == 200
    approval, approved_status = gateway_grant_post(
        "/api/gateway-grants/approve-once",
        json.dumps({"proposal_ref": proposal["proposal_ref"]}).encode(),
        owner_ref=OWNER, state_root=state_root, clock=lambda: NOW)
    assert approved_status == 200
    return {"schema": "flywheel.gateway-operation/v1",
            "journey_ref": JOURNEY, "expected_event_head": head,
            "client_request_id": request_id,
            "grant_ref": approval["grant_ref"],
            **operation, "data_refs": [], "credential_refs": []}


def test_hook_mutation_routes_are_private():
    assert is_private("/api/hooks")
    assert is_private("/api/hooks/register")
    assert is_private("/api/hooks/run")


def test_hooks_register_and_list_round_trip(tmp_path, monkeypatch):
    import harness.gateway as gateway
    _journey(tmp_path)
    monkeypatch.setattr(gateway._Handler, "run_root", str(tmp_path))
    monkeypatch.setattr(gateway._Handler, "owner_ref", OWNER)
    monkeypatch.setattr(gateway._Handler, "flywheel_home", tmp_path)
    monkeypatch.setattr(gateway._Handler, "clock", lambda *a: NOW)

    sent = _post("/api/hooks/register", _granted_body(
        tmp_path, "hook.register",
        {"event": "bench.completed", "argv": ARGS,
         "blocking": True, "hook_id": "hook_" + "a" * 8}))
    assert sent["code"] == 200
    assert sent["body"]["hook"]["hook_id"] == "hook_" + "a" * 8

    listed = _get("/api/hooks")
    assert listed["code"] == 200
    assert listed["body"]["count"] == 1
    assert listed["body"]["hooks"][0]["argv"] == ARGS


def test_hooks_register_refuses_a_secret_shaped_command(tmp_path,
                                                        monkeypatch):
    state_root, head = _journey(tmp_path)
    result, status = gateway_grant_post(
        "/api/gateway-grants/prepare/hook.register",
        json.dumps({"schema": "flywheel.gateway-operation/v1",
                    "journey_ref": JOURNEY,
                    "expected_event_head": head,
                    "client_request_id": "register-secret",
                    "operation": {"event": "bench.completed",
                                  "argv": ["python", "-c",
                                           "read the API_KEY"],
                                  "blocking": False,
                                  "hook_id": "hook_" + "b" * 8,
                                  "data_refs": [],
                                  "credential_refs": []}}).encode(),
        owner_ref=OWNER, state_root=state_root, clock=lambda: NOW)
    assert status == 422
    assert result["error"]["code"] == "INVALID_REQUEST"


def test_hooks_run_fires_and_reports_blocked(tmp_path, monkeypatch):
    import harness.gateway as gateway
    import harness.hooks_route as hooks_route
    from harness.accountable_hooks import load_registry
    _journey(tmp_path)
    monkeypatch.setattr(gateway._Handler, "run_root", str(tmp_path))
    monkeypatch.setattr(gateway._Handler, "owner_ref", OWNER)
    monkeypatch.setattr(gateway._Handler, "flywheel_home", tmp_path)
    monkeypatch.setattr(gateway._Handler, "clock", lambda *a: NOW)
    monkeypatch.setattr(hooks_route, "subprocess_runner",
                        lambda timeout_s=30.0: (
                            lambda _argv: {"exit_code": 3, "output": ""}))
    _post("/api/hooks/register", _granted_body(
        tmp_path, "hook.register",
        {"event": "bench.completed",
         "argv": ["python", "-c", "import sys; sys.exit(3)"],
         "blocking": True, "hook_id": "hook_" + "c" * 8},
        request_id="register-1"))
    sent = _post("/api/hooks/run", _granted_body(
        tmp_path, "hook.run",
        {"event": "bench.completed",
         "context": {"bench_sha256": "a" * 64},
         "registrations": load_registry(
             tmp_path / "hooks" / "registry.json")},
        request_id="run-1"))
    assert sent["code"] == 200
    assert sent["body"]["event_blocked"] is True
    assert sent["body"]["hook_receipts"][0]["exit_code"] == 3


def test_hooks_register_and_run_require_exact_grants(tmp_path, monkeypatch):
    import harness.gateway as gateway
    _journey(tmp_path)
    monkeypatch.setattr(gateway._Handler, "run_root", str(tmp_path))
    monkeypatch.setattr(gateway._Handler, "owner_ref", OWNER)
    monkeypatch.setattr(gateway._Handler, "flywheel_home", tmp_path)
    monkeypatch.setattr(gateway._Handler, "clock", lambda *a: NOW)

    register = _post("/api/hooks/register",
                     {"event": "bench.completed", "argv": ARGS,
                      "blocking": False, "hook_id": "hook_" + "d" * 8})
    run = _post("/api/hooks/run",
                {"event": "bench.completed", "context": {}})
    assert register["code"] == 403
    assert register["body"]["error"]["code"] == "PERMISSION_REQUIRED"
    assert run["code"] == 403
    assert run["body"]["error"]["code"] == "PERMISSION_REQUIRED"


def test_hook_grant_is_one_use_and_bound_to_current_head(tmp_path,
                                                        monkeypatch):
    import harness.gateway as gateway
    state_root, head = _journey(tmp_path)
    monkeypatch.setattr(gateway._Handler, "run_root", str(tmp_path))
    monkeypatch.setattr(gateway._Handler, "owner_ref", OWNER)
    monkeypatch.setattr(gateway._Handler, "flywheel_home", tmp_path)
    monkeypatch.setattr(gateway._Handler, "clock", lambda *a: NOW)
    operation = {"event": "bench.completed", "argv": ARGS,
                 "blocking": False, "hook_id": "hook_" + "e" * 8}
    granted = _granted_body(
        tmp_path, "hook.register", operation, request_id="register-replay",
        head=head)
    first = _post("/api/hooks/register", granted)
    replay = _post("/api/hooks/register", granted)
    assert first["code"] == 200
    assert replay["code"] == 403
    assert replay["body"]["error"]["code"] == "APPROVAL_EXPIRED"

    stale = _granted_body(
        tmp_path, "hook.register",
        {**operation, "hook_id": "hook_" + "f" * 8},
        request_id="register-stale")
    JourneyStore(state_root).append(MutationCommand(
        OWNER, JOURNEY, stale["expected_event_head"], "append-1",
        "decomposed", {"payload": {}, "occurred_at": NOW}))
    refused = _post("/api/hooks/register", stale)
    assert refused["code"] == 409
    assert refused["body"]["error"]["code"] == "HEAD_CONFLICT"


def test_registering_a_hook_does_not_execute_registered_hooks(
        tmp_path, monkeypatch):
    import harness.gateway as gateway
    import harness.hooks_route as hooks_route
    from harness.accountable_hooks import register_hook, save_registry
    _journey(tmp_path)
    save_registry([register_hook(
        event="hook.registered", argv=ARGS, blocking=True,
        hook_id="hook_" + "f" * 8, created_at=NOW)],
        registry_path=tmp_path / "hooks" / "registry.json")
    monkeypatch.setattr(gateway._Handler, "run_root", str(tmp_path))
    monkeypatch.setattr(gateway._Handler, "owner_ref", OWNER)
    monkeypatch.setattr(gateway._Handler, "flywheel_home", tmp_path)
    monkeypatch.setattr(gateway._Handler, "clock", lambda *a: NOW)
    monkeypatch.setattr(hooks_route, "subprocess_runner",
                        lambda *_a, **_kw: pytest.fail(
                            "registration executed a hook"))

    sent = _post("/api/hooks/register", _granted_body(
        tmp_path, "hook.register",
        {"event": "bench.completed", "argv": ARGS, "blocking": False,
         "hook_id": "hook_" + "g" * 8}))
    assert sent["code"] == 200
    assert sent["body"]["hook_receipts"] == []


def test_path_qualified_shell_is_refused_before_proposal(tmp_path):
    state_root, head = _journey(tmp_path)
    result, status = gateway_grant_post(
        "/api/gateway-grants/prepare/hook.register",
        json.dumps({"schema": "flywheel.gateway-operation/v1",
                    "journey_ref": JOURNEY,
                    "expected_event_head": head,
                    "client_request_id": "register-shell",
                    "operation": {"event": "bench.completed",
                                  "argv": [r"C:\Windows\System32\cmd.exe",
                                           "/c", "echo hi"],
                                  "blocking": False,
                                  "hook_id": "hook_" + "h" * 8,
                                  "data_refs": [],
                                  "credential_refs": []}}).encode(),
        owner_ref=OWNER, state_root=state_root, clock=lambda: NOW)
    assert status == 422
    assert result["error"]["code"] == "INVALID_REQUEST"


def test_unknown_hook_route_is_404(tmp_path):
    sent = _post("/api/hooks/explode", {})
    assert sent["code"] == 404

"""Hook run grants bind the exact sealed rows they execute."""
import io
import json

import pytest

import harness.hooks_route as hooks_route
from harness.accountable_hooks import register_hook, run_hooks, save_registry
from harness.gateway_auth import DEFAULT_HOSTS
from harness.gateway_custody import is_private
from harness.gateway_grant_route import gateway_grant_post
from harness.journey_store import JourneyStore, MutationCommand

NOW = "2026-08-24T12:00:00Z"
OWNER = "owner_" + "a" * 32
JOURNEY = "jrn_" + "a" * 32
TOKEN = "t" * 43


class _Headers:
    def __init__(self, values):
        self._values = values

    def get(self, key, default=None):
        return self._values.get(key, default)


def _journey(tmp_path):
    state_root = tmp_path / "state"
    event = JourneyStore(state_root).create(MutationCommand(
        OWNER, JOURNEY, None, "genesis", "intake",
        {"legacy_label": None, "goal": "hooks", "intake": {},
         "occurred_at": NOW}))
    return state_root, event.event_head_sha256


def _reg(hook_id, argv, event="bench.completed", blocking=False):
    return register_hook(event=event, argv=argv, blocking=blocking,
                         hook_id=hook_id, created_at=NOW)


def _registry_path(tmp_path):
    return tmp_path / "hooks" / "registry.json"


def _write_raw_registry(tmp_path, rows):
    path = _registry_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows), encoding="utf-8")


def _run_operation(registrations, event="bench.completed"):
    return {"event": event, "context": {"bench_sha256": "a" * 64},
            "registrations": registrations}


def _approved_run(tmp_path, state_root, head, operation, request_id="run-1"):
    proposal, status = gateway_grant_post(
        "/api/gateway-grants/prepare/hook.run",
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
            "journey_ref": JOURNEY,
            "expected_event_head": head,
            "client_request_id": request_id,
            "grant_ref": approval["grant_ref"],
            **operation, "data_refs": [], "credential_refs": []}


def _run_post(tmp_path, state_root, body):
    return hooks_route.handle_hooks_post(
        "/api/hooks/run", json.dumps(body).encode(), run_root=tmp_path,
        owner_ref=OWNER, state_root=state_root, clock=lambda: NOW)


def _gateway_get(tmp_path, auth_token="", authorization=None):
    import harness.gateway as gateway
    h = gateway._Handler.__new__(gateway._Handler)
    h.command = "GET"
    h.path = "/api/hooks"
    headers = {"Content-Length": "0", "Host": "localhost"}
    if authorization is not None:
        headers["Authorization"] = authorization
    h.headers = _Headers(headers)
    h.rfile = io.BytesIO(b"")
    h.wfile = io.BytesIO()
    h.run_root = str(tmp_path)
    h.owner_ref = OWNER
    h.flywheel_home = tmp_path
    h.auth_token = auth_token
    h.allowed_hosts = DEFAULT_HOSTS
    h.clock = lambda *a: NOW
    sent = {}
    h._json = lambda b, code=200: sent.update(body=b, code=code)
    statuses = []
    h.send_response = lambda code: statuses.append(code)
    h.send_header = lambda *_a, **_kw: None
    h.end_headers = lambda: None
    h.do_GET()
    if sent:
        return sent
    return {"code": statuses[-1], "body": json.loads(h.wfile.getvalue())}


def test_hooks_registry_get_is_private_but_bearer_auth_still_lists(
        tmp_path):
    assert is_private("/api/hooks")
    save_registry([_reg("hook_" + "a" * 8, ["python", "-c", "print(1)"])],
                  registry_path=_registry_path(tmp_path))
    refused = _gateway_get(tmp_path)
    assert refused["code"] == 401
    assert refused["body"]["error"]["code"] == "AUTH_REQUIRED"
    listed = _gateway_get(tmp_path, auth_token=TOKEN,
                          authorization=f"Bearer {TOKEN}")
    assert listed["code"] == 200
    assert listed["body"]["count"] == 1


@pytest.mark.parametrize("change", ["replace", "add", "delete"])
def test_approved_hook_run_refuses_registry_drift_before_runner(
        tmp_path, monkeypatch, change):
    state_root, head = _journey(tmp_path)
    first = _reg("hook_" + "b" * 8,
                 ["python", "-c", "print('approved')"])
    second = _reg("hook_" + "c" * 8,
                  ["python", "-c", "print('second')"])
    approved_rows = [first, second] if change == "delete" else [first]
    save_registry(approved_rows, registry_path=_registry_path(tmp_path))
    granted = _approved_run(
        tmp_path, state_root, head, _run_operation(approved_rows),
        request_id=f"run-drift-{change}")
    if change == "replace":
        current = [_reg("hook_" + "b" * 8,
                        ["python", "-c", "print('changed')"])]
    elif change == "add":
        current = [first, second]
    else:
        current = [first]
    save_registry(current, registry_path=_registry_path(tmp_path))
    monkeypatch.setattr(hooks_route, "subprocess_runner",
                        lambda *_a, **_kw: pytest.fail(
                            "stale hook.run grant reached a runner"))
    body, status = _run_post(tmp_path, state_root, granted)
    assert status == 409
    assert body["error"]["code"] == "REGISTRY_CONFLICT"


@pytest.mark.parametrize("event", [
    ["bench.completed"], {"bad": "bench.completed"}, "", "on.everything"])
def test_hook_run_prepare_rejects_non_allowlisted_event(tmp_path, event):
    state_root, head = _journey(tmp_path)
    result, status = gateway_grant_post(
        "/api/gateway-grants/prepare/hook.run",
        json.dumps({"schema": "flywheel.gateway-operation/v1",
                    "journey_ref": JOURNEY,
                    "expected_event_head": head,
                    "client_request_id": "bad-event",
                    "operation": {"event": event, "context": {},
                                  "data_refs": [],
                                  "credential_refs": []}}).encode(),
        owner_ref=OWNER, state_root=state_root, clock=lambda: NOW)
    assert status == 422
    assert result["error"]["code"] == "INVALID_REQUEST"


def test_hook_run_prepare_rejects_generic_event_grant(tmp_path):
    state_root, head = _journey(tmp_path)
    result, status = gateway_grant_post(
        "/api/gateway-grants/prepare/hook.run",
        json.dumps({"schema": "flywheel.gateway-operation/v1",
                    "journey_ref": JOURNEY,
                    "expected_event_head": head,
                    "client_request_id": "generic-event",
                    "operation": {"event": "bench.completed",
                                  "context": {},
                                  "data_refs": [],
                                  "credential_refs": []}}).encode(),
        owner_ref=OWNER, state_root=state_root, clock=lambda: NOW)
    assert status == 422
    assert result["error"]["code"] == "INVALID_REQUEST"


def test_hook_run_prepare_rejects_registration_event_mismatch(tmp_path):
    state_root, head = _journey(tmp_path)
    result, status = gateway_grant_post(
        "/api/gateway-grants/prepare/hook.run",
        json.dumps({"schema": "flywheel.gateway-operation/v1",
                    "journey_ref": JOURNEY,
                    "expected_event_head": head,
                    "client_request_id": "event-mismatch",
                    "operation": {**_run_operation([
                        _reg("hook_" + "d" * 8,
                             ["python", "-c", "print('other')"],
                             event="agent.completed")]),
                        "data_refs": [], "credential_refs": []}}).encode(),
        owner_ref=OWNER, state_root=state_root, clock=lambda: NOW)
    assert status == 422
    assert result["error"]["code"] == "INVALID_REQUEST"


def test_hook_run_prepare_summary_names_selected_commands(tmp_path):
    state_root, head = _journey(tmp_path)
    row = _reg("hook_" + "e" * 8,
               ["python", "-c", "print('summary')"])
    proposal, status = gateway_grant_post(
        "/api/gateway-grants/prepare/hook.run",
        json.dumps({"schema": "flywheel.gateway-operation/v1",
                    "journey_ref": JOURNEY,
                    "expected_event_head": head,
                    "client_request_id": "summary",
                    "operation": {**_run_operation([row]),
                                  "data_refs": [],
                                  "credential_refs": []}}).encode(),
        owner_ref=OWNER, state_root=state_root, clock=lambda: NOW)
    assert status == 200
    assert proposal["destination"]["ref"].startswith("bench.completed:1:")
    assert proposal["summary"]["hook_registrations"] == [{
        "hook_id": row["hook_id"], "hook_sha256": row["hook_sha256"],
        "argv": row["argv"], "blocking": row["blocking"]}]


def test_hook_run_reports_tampered_current_registry_before_runner(
        tmp_path, monkeypatch):
    state_root, head = _journey(tmp_path)
    row = _reg("hook_" + "f" * 8,
               ["python", "-c", "print('approved')"])
    save_registry([row], registry_path=_registry_path(tmp_path))
    granted = _approved_run(
        tmp_path, state_root, head, _run_operation([row]),
        request_id="run-tampered-current")
    tampered = dict(row)
    tampered["argv"] = ["python", "-c", "print('tampered')"]
    _write_raw_registry(tmp_path, [tampered])
    monkeypatch.setattr(hooks_route, "subprocess_runner",
                        lambda *_a, **_kw: pytest.fail(
                            "tampered current registry reached a runner"))
    body, status = _run_post(tmp_path, state_root, granted)
    assert status == 409
    assert body["error"]["code"] == "REGISTRY_CONFLICT"


def test_hooks_get_reports_tampered_registry_as_protocol_error(tmp_path):
    row = _reg("hook_" + "g" * 8, ["python", "-c", "print('listed')"])
    row["argv"] = ["python", "-c", "print('tampered')"]
    _write_raw_registry(tmp_path, [row])
    body, status = hooks_route.handle_hooks_get(
        "/api/hooks", run_root=tmp_path)
    assert status == 422
    assert body["error"]["code"] == "INVALID_REQUEST"


def test_run_hooks_refuses_unsealed_rows_before_event_matching():
    bad = dict(_reg("hook_" + "e" * 8,
                   ["python", "-c", "print('bad')"],
                   event="agent.completed"))
    bad["argv"] = ["python", "-c", "print('tampered')"]
    with pytest.raises(ValueError):
        run_hooks("bench.completed", [bad],
                  runner=lambda _argv: pytest.fail(
                      "unsealed nonmatching row was not validated"),
                  context={})

import hashlib
import io
import json
import time

from harness import gateway
from harness.credential_handles import CredentialHandleStore
from harness.gateway_grant_route import gateway_grant_post
from harness.gateway_operation import canonicalize_operation
from harness.journey_store import JourneyStore, MutationCommand
from harness.live_screen_feed import LiveScreenManager, SourceDescriptor, SyntheticCaptureSource
from harness.live_screen_gateway_mount import live_screen_post

NOW = "2026-09-15T12:00:00Z"
OWNER = "owner_" + "a" * 32
OTHER_OWNER = "owner_" + "b" * 32
JOURNEY = "jrn_" + "a" * 32
SECRET = "sk-synthetic-bound-secret"


class _FakeResponse:
    status = 200
    fp = None

    def __init__(self):
        self._body = json.dumps({"id": "resp_live_bound_1", "output": []}).encode()
        self._done = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read1(self, _size):
        if self._done:
            return b""
        self._done = True
        return self._body


class _FakeOpener:
    def __init__(self):
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        return _FakeResponse()


class _Headers:
    def __init__(self, raw):
        self.raw = raw

    def get(self, key, default=None):
        return str(len(self.raw)) if key == "Content-Length" else default


def _journey(state):
    return JourneyStore(state / "state").create(MutationCommand(
        OWNER, JOURNEY, None, "create-1", "intake",
        {"legacy_label": None, "goal": "screen model body loop",
         "intake": {}, "occurred_at": NOW})).event_head_sha256


def _manager():
    manager = LiveScreenManager(clock_ns=lambda: 1_000_000_000,
                                utc_clock=lambda: "2026-09-15T12:00:00Z")
    manager.register_source(
        SourceDescriptor("display:primary", "display", "Primary display",
                         bounds=(0, 0, 4, 4), backend="synthetic"),
        lambda: SyntheticCaptureSource("display:primary", [b"\x89PNG\r\nbound-frame"],
                                       width=4, height=4),
    )
    return manager


def _handler(tmp_path, raw=b"{}"):
    h = gateway._Handler.__new__(gateway._Handler)
    h.owner_ref = OWNER
    h.flywheel_home = tmp_path
    h.run_root = str(tmp_path)
    h.root = tmp_path
    h.clock = lambda: NOW
    h.headers = _Headers(raw)
    h.rfile = io.BytesIO(raw)
    sent = {}
    h._json = lambda body, code=200: sent.update(kind="json", body=body, code=code)
    return h, sent


def _bind_openai(state):
    return CredentialHandleStore(
        state / "state",
        keychain_get=lambda slot: "setup" if slot == "OPENAI_API_KEY" else None,
        token_hex=lambda _size: "a" * 32,
    ).bind(OWNER, "OPENAI_API_KEY").credential_ref


def _approved_final(state, action, operation, request_id):
    grant_state = state / "state"
    head = JourneyStore(grant_state).load(OWNER, JOURNEY)["event_head_sha256"]
    prepare = {"schema": "flywheel.gateway-operation/v1", "journey_ref": JOURNEY,
               "expected_event_head": head, "client_request_id": request_id,
               "operation": operation}
    proposal, status = gateway_grant_post(
        f"/api/gateway-grants/prepare/{action}",
        json.dumps(prepare).encode(), owner_ref=OWNER, state_root=grant_state,
        clock=lambda: NOW, workspace_root=state)
    assert status == 200, proposal
    approval, status = gateway_grant_post(
        "/api/gateway-grants/approve-once",
        json.dumps({"proposal_ref": proposal["proposal_ref"]}).encode(),
        owner_ref=OWNER, state_root=grant_state, clock=lambda: NOW)
    assert status == 200, approval
    final = {key: value for key, value in prepare.items() if key != "operation"}
    final.update(operation)
    final["grant_ref"] = approval["grant_ref"]
    return json.dumps(final, separators=(",", ":")).encode()


def _open_operation():
    return {
        "control": "open",
        "body_session_ref": "studio-screen-1",
        "instrument_ref": "screen",
        "sources": [{"source_id": "display:primary"}],
        "destination": "openai_responses:vision",
        "model": "gpt-6-astra",
        "delivery_mode": "sampled_image",
        "expires_after_ms": 5000,
        "buffer_frames_per_source": 2,
        "max_frame_bytes": 1024,
        "start_immediately": True,
        "data_refs": [],
        "credential_refs": [],
    }


def _delivery_operation(session_id, credential_ref):
    return {
        "session_id": session_id,
        "source_id": "display:primary",
        "destination": "openai_responses:vision",
        "model": "gpt-6-astra",
        "delivery_mode": "sampled_image",
        "prompt": "Describe the sampled screen frame for the Studio body controller.",
        "max_output_tokens": 64,
        "timeout_s": 30,
        "max_age_ms": 60_000,
        "data_refs": [],
        "credential_refs": [credential_ref],
    }


def _open_started_session(tmp_path):
    _journey(tmp_path)
    gateway._Handler.live_screen_manager = _manager()
    gateway._Handler.live_screen_scheduler = None
    gateway._Handler._live_screen_state_root = tmp_path / "state"
    h, sent = _handler(tmp_path, _approved_final(
        tmp_path, "live_screen.control", _open_operation(), "open-start-1"))
    live_screen_post(h, "/api/live-screen/sessions", now_ns=1_100_000_000)
    assert sent["code"] == 200
    return sent["body"]["session_id"]


def test_deliver_operation_requires_provider_credentials_and_review_scope(tmp_path):
    _journey(tmp_path)
    credential_ref = _bind_openai(tmp_path)
    op = canonicalize_operation("live_screen.deliver",
                                _delivery_operation("screen-session-1", credential_ref))

    assert op.scopes == ("network", "secrets")
    assert dict(op.destination) == {
        "kind": "live-screen-delivery",
        "ref": "deliver:screen-session-1:gpt-6-astra",
    }

    bad = {**_delivery_operation("screen-session-1", credential_ref),
           "credential_refs": []}
    try:
        canonicalize_operation("live_screen.deliver", bad)
    except Exception as exc:
        assert getattr(exc, "code", "") == "INVALID_REQUEST"
    else:
        raise AssertionError("sampled image delivery must require an explicit credential handle")


def test_gateway_delivery_resolves_server_side_credential_and_sends_frame_bytes(
        tmp_path, monkeypatch):
    session_id = _open_started_session(tmp_path)
    credential_ref = _bind_openai(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-must-not-be-used")
    monkeypatch.setattr("harness.keychain.resolve_credential",
                        lambda slot: SECRET if slot == "OPENAI_API_KEY" else "")
    opener = _FakeOpener()
    raw = _approved_final(tmp_path, "live_screen.deliver",
                          _delivery_operation(session_id, credential_ref), "deliver-1")
    h, sent = _handler(tmp_path, raw)
    h.provider_opener = opener

    live_screen_post(
        h, f"/api/live-screen/sessions/{session_id}/sources/display%3Aprimary/deliver",
        now_ns=1_200_000_000)

    assert sent["code"] == 200
    receipt = sent["body"]["receipt"]
    assert sent["body"]["schema"] == "flywheel.live-screen-delivery/v1"
    assert receipt["event"] == "screen.delivery"
    assert receipt["frame"]["source_id"] == "display:primary"
    assert receipt["provider_response_id"] == "resp_live_bound_1"
    assert receipt["provider_binding"] == {
        "provider": "openai",
        "model_route": "openai_responses:vision",
        "model": "gpt-6-astra",
        "credential_ref_count": 1,
        "credential_refs_sha256": hashlib.sha256(
            json.dumps([credential_ref], separators=(",", ":")).encode()).hexdigest(),
    }
    assert SECRET not in json.dumps(sent["body"])
    request, timeout = opener.requests[0]
    assert 0 < timeout <= 30
    assert request.headers["Authorization"] == "Bearer " + SECRET
    assert "ambient-must-not-be-used" not in json.dumps(json.loads(request.data))
    image_part = json.loads(request.data)["input"][0]["content"][1]
    assert image_part["type"] == "input_image"


def test_unowned_delivery_credential_fails_before_provider_transport(tmp_path):
    _journey(tmp_path)
    store = CredentialHandleStore(
        tmp_path / "state", keychain_get=lambda _slot: "setup",
        token_hex=lambda _size: "b" * 32)
    credential_ref = store.bind(OTHER_OWNER, "OPENAI_API_KEY").credential_ref
    operation = _delivery_operation("screen-session-1", credential_ref)
    head = JourneyStore(tmp_path / "state").load(OWNER, JOURNEY)["event_head_sha256"]
    proposal, status = gateway_grant_post(
        "/api/gateway-grants/prepare/live_screen.deliver",
        json.dumps({"schema": "flywheel.gateway-operation/v1",
                    "journey_ref": JOURNEY, "expected_event_head": head,
                    "client_request_id": "deliver-bad",
                    "operation": operation}).encode(),
        owner_ref=OWNER, state_root=tmp_path / "state", clock=lambda: NOW,
        workspace_root=tmp_path)
    assert status == 403
    assert proposal["error"]["code"] == "PERMISSION_REQUIRED"

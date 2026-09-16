import hashlib
import io
import json

from harness import gateway
from harness.gateway_grant_route import gateway_grant_post
from harness.gateway_operation import canonicalize_operation
from harness.journey_store import JourneyStore, MutationCommand
from harness.live_screen_feed import LiveScreenManager, SourceDescriptor, SyntheticCaptureSource
from harness.live_screen_gateway_mount import (
    live_screen_get,
    live_screen_post,
    validate_model_delivery,
)
from harness.studio_body_route import handle_body_post

NOW = "2026-09-15T12:00:00Z"
OWNER = "owner_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
JOURNEY = "jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def _journey(state):
    return JourneyStore(state / "state").create(MutationCommand(
        OWNER, JOURNEY, None, "create-1", "intake",
        {"legacy_label": None, "goal": "live screen body",
         "intake": {}, "occurred_at": NOW})).event_head_sha256


def _operation(control, **extra):
    body = {"control": control, "data_refs": [], "credential_refs": []}
    body.update(extra)
    return body


def _open_operation():
    return _operation(
        "open",
        body_session_ref="body-session-1",
        instrument_ref="instrument-1",
        sources=[{"source_id": "display:primary"}],
        destination="openai_responses:vision",
        model="gpt-6-astra",
        delivery_mode="sampled_image",
        expires_after_ms=5000,
        buffer_frames_per_source=2,
        max_frame_bytes=64,
    )


def _approved_final(state, operation, request_id):
    grant_state = state / "state"
    head = JourneyStore(grant_state).load(OWNER, JOURNEY)["event_head_sha256"]
    prepare = {"schema": "flywheel.gateway-operation/v1", "journey_ref": JOURNEY,
               "expected_event_head": head, "client_request_id": request_id,
               "operation": operation}
    proposal, status = gateway_grant_post(
        "/api/gateway-grants/prepare/live_screen.control",
        json.dumps(prepare).encode(), owner_ref=OWNER, state_root=grant_state,
        clock=lambda: NOW)
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


def _manager():
    manager = LiveScreenManager(clock_ns=lambda: 1_000_000_000,
                                utc_clock=lambda: "2026-09-15T12:00:00Z")
    manager.register_source(
        SourceDescriptor("display:primary", "display", "Primary display",
                         bounds=(0, 0, 16, 16), backend="synthetic"),
        lambda: SyntheticCaptureSource("display:primary", [b"frame-a"], width=16, height=16),
    )
    return manager


def _handler(tmp_path, raw=b"{}"):
    h = gateway._Handler.__new__(gateway._Handler)
    h.owner_ref = OWNER
    h.flywheel_home = tmp_path
    h.run_root = str(tmp_path)
    h.root = tmp_path
    h.clock = lambda: NOW
    h.headers = type("Headers", (), {"get": lambda _self, key, default=None: str(len(raw)) if key == "Content-Length" else default})()
    h.rfile = io.BytesIO(raw)
    sent = {}
    h._json = lambda body, code=200: sent.update(kind="json", body=body, code=code)
    h._raw = lambda body, content_type, code=200, extra_headers=None: sent.update(
        kind="raw", body=body, content_type=content_type, code=code,
        extra_headers=extra_headers or {})
    return h, sent


def test_live_screen_control_is_grantable_but_native_video_is_not_claimed():
    op = canonicalize_operation("live_screen.control", _open_operation())

    assert op.scopes == ("write",)
    assert dict(op.destination) == {
        "kind": "live-screen",
        "ref": "open:openai_responses:vision:gpt-6-astra",
    }
    start = canonicalize_operation(
        "live_screen.control",
        _operation("start", session_id="screen-session-1"),
    )
    assert dict(start.destination) == {
        "kind": "live-screen",
        "ref": "session:screen-session-1:start",
    }

    bad = {**_open_operation(), "delivery_mode": "native_video"}
    try:
        canonicalize_operation("live_screen.control", bad)
    except Exception as exc:
        assert getattr(exc, "code", "") == "INVALID_REQUEST"
    else:
        raise AssertionError("native_video must remain unavailable until a video transport exists")

    with_credentials = {**_operation("start", session_id="screen-session-1"),
                        "credential_refs": ["cred_" + "a" * 32]}
    try:
        canonicalize_operation("live_screen.control", with_credentials)
    except Exception as exc:
        assert getattr(exc, "code", "") == "INVALID_REQUEST"
    else:
        raise AssertionError("capture controls must not carry provider credentials")


def test_gateway_lifecycle_uses_grants_and_scheduler_before_poll(tmp_path):
    _journey(tmp_path)
    gateway._Handler.live_screen_manager = _manager()
    gateway._Handler.live_screen_scheduler = None
    gateway._Handler._live_screen_state_root = tmp_path / "state"

    raw = _approved_final(tmp_path, _open_operation(), "open-1")
    h, sent = _handler(tmp_path, raw)
    live_screen_post(h, "/api/live-screen/sessions", now_ns=1_100_000_000)
    assert sent["code"] == 200
    session_id = sent["body"]["session_id"]

    raw = _approved_final(tmp_path, _operation("start", session_id=session_id), "start-1")
    h, sent = _handler(tmp_path, raw)
    live_screen_post(h, f"/api/live-screen/sessions/{session_id}/start", now_ns=1_200_000_000)
    assert sent["code"] == 200 and sent["body"]["state"] == "active"

    h, sent = _handler(tmp_path, b"{}")
    live_screen_post(h, f"/api/live-screen/sessions/{session_id}/poll", now_ns=1_300_000_000)
    assert sent["code"] == 200
    assert sent["body"]["events"][0]["source_id"] == "display:primary"

    h, sent = _handler(tmp_path)
    live_screen_get(
        h,
        f"/api/live-screen/sessions/{session_id}/sources/display%3Aprimary/frames/1/preview",
        now_ns=1_400_000_000,
    )
    assert sent["kind"] == "raw"
    assert sent["body"] == b"frame-a"
    assert sent["content_type"] == "image/png"
    assert sent["extra_headers"]["X-Frame-Sha256"] == hashlib.sha256(b"frame-a").hexdigest()

    h, sent = _handler(tmp_path)
    h.owner_ref = "owner_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    live_screen_get(
        h,
        f"/api/live-screen/sessions/{session_id}/sources/display%3Aprimary/frames/1/preview",
        now_ns=1_400_000_000,
    )
    assert sent["kind"] == "json"
    assert sent["code"] == 403
    assert sent["body"]["error"]["code"] == "OWNER_NOT_AUTHORIZED"

    h, sent = _handler(tmp_path)
    live_screen_get(
        h,
        f"/api/live-screen/sessions/{session_id}/sources/display%253Aprimary/frames/1/preview",
        now_ns=1_400_000_000,
    )
    assert sent["kind"] == "json"
    assert sent["code"] == 400
    assert sent["body"]["error"]["code"] == "INVALID_ID"

    raw = _approved_final(tmp_path, _operation("stop", session_id=session_id), "stop-1")
    h, sent = _handler(tmp_path, raw)
    live_screen_post(h, f"/api/live-screen/sessions/{session_id}/stop", now_ns=1_500_000_000)
    assert sent["code"] == 200 and sent["body"]["state"] == "stopped"


def test_body_snapshot_uses_backend_live_frame_identity(tmp_path):
    _journey(tmp_path)
    manager = _manager()
    gateway._Handler.live_screen_manager = manager
    gateway._Handler.live_screen_scheduler = None
    gateway._Handler._live_screen_state_root = tmp_path / "state"

    raw = _approved_final(tmp_path, _open_operation(), "open-1")
    h, sent = _handler(tmp_path, raw)
    live_screen_post(h, "/api/live-screen/sessions", now_ns=1_100_000_000)
    session_id = sent["body"]["session_id"]
    scheduler = gateway._Handler.live_screen_scheduler

    raw = _approved_final(tmp_path, _operation("start", session_id=session_id), "start-1")
    h, sent = _handler(tmp_path, raw)
    live_screen_post(h, f"/api/live-screen/sessions/{session_id}/start", now_ns=1_200_000_000)
    frame = manager.latest_frame(session_id, "display:primary", owner_ref=OWNER,
                                 now_ns=1_250_000_000)

    body, code = handle_body_post("/api/studio/body/snapshot", {
        "session_ref": "body-session-1",
        "instrument_ref": "instrument-1",
        "capture_session_ref": session_id,
        "source_ref": "display:primary",
        "latest_frame_ref": "caller-supplied-value",
    }, clock=lambda: NOW, capture_manager=manager, capture_scheduler=scheduler,
       owner_ref=OWNER, now_ns=1_250_000_000)

    assert code == 200
    snapshot = body["snapshot"]
    assert snapshot["latest_frame_ref"] == "display:primary:1"
    assert snapshot["capture"]["available"] is True
    assert snapshot["capture"]["validated"] is True
    assert snapshot["capture"]["frame_sha256"] == frame.frame_sha256
    assert snapshot["requested_capture"]["latest_frame_ref"] == "caller-supplied-value"


def test_model_delivery_requires_exact_backend_frame_identity(tmp_path):
    _journey(tmp_path)
    manager = _manager()
    gateway._Handler.live_screen_manager = manager
    gateway._Handler.live_screen_scheduler = None
    gateway._Handler._live_screen_state_root = tmp_path / "state"

    raw = _approved_final(tmp_path, _open_operation(), "open-1")
    h, sent = _handler(tmp_path, raw)
    live_screen_post(h, "/api/live-screen/sessions", now_ns=1_100_000_000)
    session_id = sent["body"]["session_id"]
    scheduler = gateway._Handler.live_screen_scheduler
    raw = _approved_final(tmp_path, _operation("start", session_id=session_id), "start-1")
    h, sent = _handler(tmp_path, raw)
    live_screen_post(h, f"/api/live-screen/sessions/{session_id}/start", now_ns=1_200_000_000)
    frame = manager.latest_frame(session_id, "display:primary", owner_ref=OWNER,
                                 now_ns=1_250_000_000)

    missing_identity = validate_model_delivery(
        manager=manager, scheduler=scheduler, owner_ref=OWNER,
        content={"session_ref": "body-session-1", "instrument_ref": "instrument-1",
                 "latest_frame_ref": "display:primary:1",
                 "model_delivery": {"parts": [{"kind": "image",
                                                "frame_ref": "display:primary:1"}]}},
        now_ns=1_250_000_000)
    assert missing_identity["validated"] is False

    verified = validate_model_delivery(
        manager=manager, scheduler=scheduler, owner_ref=OWNER,
        content={"session_ref": "body-session-1", "instrument_ref": "instrument-1",
                 "model_delivery": {"parts": [{"kind": "image",
                                                "frame": frame.identity()}]}},
        now_ns=1_250_000_000)
    assert verified == {"validated": True, "status": "validated"}


def test_scheduler_stops_expired_sessions_and_poll_does_not_capture(tmp_path):
    _journey(tmp_path)
    op = {**_open_operation(), "expires_after_ms": 1000}
    gateway._Handler.live_screen_manager = _manager()
    gateway._Handler.live_screen_scheduler = None
    gateway._Handler._live_screen_state_root = tmp_path / "state"

    raw = _approved_final(tmp_path, op, "open-1")
    h, sent = _handler(tmp_path, raw)
    live_screen_post(h, "/api/live-screen/sessions", now_ns=1_100_000_000)
    session_id = sent["body"]["session_id"]

    raw = _approved_final(tmp_path, _operation("start", session_id=session_id), "start-1")
    h, sent = _handler(tmp_path, raw)
    live_screen_post(h, f"/api/live-screen/sessions/{session_id}/start", now_ns=1_200_000_000)
    assert sent["body"]["producer"]["tick_events"] == 1
    manager = gateway._Handler.live_screen_manager
    scheduler = gateway._Handler.live_screen_scheduler
    assert manager._reserved_buffer_bytes > 0

    h, sent = _handler(tmp_path, b"{}")
    live_screen_post(h, f"/api/live-screen/sessions/{session_id}/poll", now_ns=2_200_000_000)

    assert sent["code"] == 403
    assert scheduler.active.get((session_id, OWNER)) is not True
    assert manager._reserved_buffer_bytes == 0

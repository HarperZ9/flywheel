import io
import json
import time

from harness import gateway
from harness.gateway_grant_route import gateway_grant_post
from harness.journey_store import JourneyStore, MutationCommand
from harness.live_screen_feed import LiveScreenManager, SourceDescriptor, SyntheticCaptureSource
from harness.live_screen_gateway_mount import live_screen_post
from harness.live_screen_scheduler import LiveScreenProducerScheduler

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
        buffer_frames_per_source=3,
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


def _manager(frames=None):
    frames = frames or [b"frame-a", b"frame-b", b"frame-c"]
    manager = LiveScreenManager(clock_ns=lambda: 1_000_000_000,
                                utc_clock=lambda: "2026-09-15T12:00:00Z")
    manager.register_source(
        SourceDescriptor("display:primary", "display", "Primary display",
                         bounds=(0, 0, 16, 16), backend="synthetic"),
        lambda: SyntheticCaptureSource(
            "display:primary", list(frames), width=16, height=16),
    )
    return manager


def _handler(tmp_path, raw=b"{}"):
    h = gateway._Handler.__new__(gateway._Handler)
    h.owner_ref = OWNER
    h.flywheel_home = tmp_path
    h.run_root = str(tmp_path)
    h.root = tmp_path
    h.clock = lambda: NOW
    h.headers = type("Headers", (), {
        "get": lambda _self, key, default=None: str(len(raw))
        if key == "Content-Length" else default})()
    h.rfile = io.BytesIO(raw)
    sent = {}
    h._json = lambda body, code=200: sent.update(kind="json", body=body, code=code)
    return h, sent


def test_gateway_start_schedules_producer_without_poll_capture(tmp_path):
    _journey(tmp_path)
    manager = _manager()
    gateway._Handler.live_screen_manager = manager
    gateway._Handler.live_screen_scheduler = LiveScreenProducerScheduler(
        manager, tick_interval_ms=1)
    gateway._Handler._live_screen_state_root = tmp_path / "state"

    h, sent = _handler(tmp_path, _approved_final(tmp_path, _open_operation(), "open-1"))
    live_screen_post(h, "/api/live-screen/sessions")
    assert sent["code"] == 200
    session_id = sent["body"]["session_id"]

    h, sent = _handler(tmp_path, _approved_final(
        tmp_path, _operation("start", session_id=session_id), "start-1"))
    live_screen_post(h, f"/api/live-screen/sessions/{session_id}/start")
    assert sent["body"]["producer"]["tick_events"] == 1

    deadline = time.time() + 1
    frame = None
    while time.time() < deadline:
        frame = manager.latest_frame(session_id, "display:primary",
                                     owner_ref=OWNER, now_ns=time.monotonic_ns())
        if frame and frame.source_sequence >= 2:
            break
        time.sleep(0.01)

    assert frame is not None and frame.source_sequence >= 2
    h, sent = _handler(tmp_path, b"{}")
    live_screen_post(h, f"/api/live-screen/sessions/{session_id}/poll")
    sequences = [event["source_sequence"] for event in sent["body"]["events"]]
    assert sequences[0] == 1
    assert max(sequences) >= 2


def test_open_can_start_immediately_under_one_reviewed_grant(tmp_path):
    _journey(tmp_path)
    manager = _manager()
    gateway._Handler.live_screen_manager = manager
    gateway._Handler.live_screen_scheduler = LiveScreenProducerScheduler(
        manager, tick_interval_ms=1)
    gateway._Handler._live_screen_state_root = tmp_path / "state"

    op = {**_open_operation(), "start_immediately": True}
    h, sent = _handler(tmp_path, _approved_final(tmp_path, op, "open-start-1"))
    live_screen_post(h, "/api/live-screen/sessions")

    assert sent["code"] == 200
    assert sent["body"]["state"] == "active"
    assert sent["body"]["producer"]["tick_events"] == 1
    assert sent["body"]["body_binding"] == {
        "session_ref": "body-session-1", "instrument_ref": "instrument-1"}


def test_start_immediately_cleans_created_session_on_startup_failure(tmp_path):
    _journey(tmp_path)
    manager = _manager([b"too-large"])
    gateway._Handler.live_screen_manager = manager
    gateway._Handler.live_screen_scheduler = LiveScreenProducerScheduler(
        manager, tick_interval_ms=1)
    gateway._Handler._live_screen_state_root = tmp_path / "state"

    op = {**_open_operation(), "start_immediately": True, "max_frame_bytes": 1}
    h, sent = _handler(tmp_path, _approved_final(tmp_path, op, "open-start-1"))
    live_screen_post(h, "/api/live-screen/sessions")

    assert sent["code"] == 400
    assert sent["body"]["error"]["code"] == "FRAME_TOO_LARGE"
    assert manager._reserved_buffer_bytes == 0
    assert {session.state for session in manager._sessions.values()} == {"stopped"}

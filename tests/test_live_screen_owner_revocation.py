import io
import json

from harness import gateway
from harness.gateway_grant_route import gateway_grant_post
from harness.journey_store import JourneyStore, MutationCommand
from harness.live_screen_feed import LiveScreenManager, SourceDescriptor, SyntheticCaptureSource
from harness.live_screen_gateway_mount import live_screen_post


NOW = "2026-09-15T12:00:00Z"
OWNER = "owner_" + "a" * 32
OTHER_OWNER = "owner_" + "b" * 32
JOURNEY = "jrn_" + "a" * 32


def _journey(root):
    JourneyStore(root / "state").create(MutationCommand(
        OWNER, JOURNEY, None, "create-1", "intake",
        {"legacy_label": None, "goal": "revocation-only stop",
         "intake": {}, "occurred_at": NOW}))


def _manager():
    manager = LiveScreenManager(clock_ns=lambda: 1_000_000_000,
                                utc_clock=lambda: "2026-09-15T12:00:00Z")
    manager.register_source(
        SourceDescriptor("display:primary", "display", "Primary display",
                         bounds=(0, 0, 2, 2), backend="synthetic"),
        lambda: SyntheticCaptureSource("display:primary", [b"frame"], width=2, height=2),
    )
    return manager


def _handler(root, raw=b"{}"):
    h = gateway._Handler.__new__(gateway._Handler)
    h.owner_ref = OWNER
    h.flywheel_home = root
    h.run_root = str(root)
    h.root = root
    h.clock = lambda: NOW
    h.headers = type("Headers", (), {
        "get": lambda _self, key, default=None: str(len(raw)) if key == "Content-Length" else default
    })()
    h.rfile = io.BytesIO(raw)
    sent = {}
    h._json = lambda body, code=200: sent.update(body=body, code=code)
    return h, sent


def _approved(root, operation, request_id):
    head = JourneyStore(root / "state").load(OWNER, JOURNEY)["event_head_sha256"]
    prepare = {"schema": "flywheel.gateway-operation/v1",
               "journey_ref": JOURNEY, "expected_event_head": head,
               "client_request_id": request_id, "operation": operation}
    proposal, status = gateway_grant_post(
        "/api/gateway-grants/prepare/live_screen.control",
        json.dumps(prepare).encode(), owner_ref=OWNER,
        state_root=root / "state", clock=lambda: NOW, workspace_root=root)
    assert status == 200, proposal
    approval, status = gateway_grant_post(
        "/api/gateway-grants/approve-once",
        json.dumps({"proposal_ref": proposal["proposal_ref"]}).encode(),
        owner_ref=OWNER, state_root=root / "state", clock=lambda: NOW)
    assert status == 200, approval
    final = {key: value for key, value in prepare.items() if key != "operation"}
    final.update(operation)
    final["grant_ref"] = approval["grant_ref"]
    return json.dumps(final, separators=(",", ":")).encode()


def _open_start(root):
    _journey(root)
    gateway._Handler.live_screen_manager = _manager()
    gateway._Handler.live_screen_scheduler = None
    gateway._Handler._live_screen_state_root = root / "state"
    open_op = {"control": "open", "body_session_ref": "studio-screen-1",
               "instrument_ref": "screen", "sources": [{"source_id": "display:primary"}],
               "destination": "openai_responses:vision", "model": "gpt-6-astra",
               "delivery_mode": "sampled_image", "expires_after_ms": 5000,
               "start_immediately": True, "data_refs": [], "credential_refs": []}
    h, sent = _handler(root, _approved(root, open_op, "open-1"))
    live_screen_post(h, "/api/live-screen/sessions", now_ns=1_100_000_000)
    assert sent["code"] == 200
    return sent["body"]["session_id"]


def test_owner_can_pause_and_stop_without_new_journey_grant(tmp_path):
    session_id = _open_start(tmp_path)

    h, sent = _handler(tmp_path, b"{}")
    live_screen_post(h, f"/api/live-screen/sessions/{session_id}/pause",
                     now_ns=1_200_000_000)
    assert sent["code"] == 200
    assert sent["body"]["state"] == "paused"

    h, sent = _handler(tmp_path, b"{}")
    live_screen_post(h, f"/api/live-screen/sessions/{session_id}/stop",
                     now_ns=1_300_000_000)
    assert sent["code"] == 200
    assert sent["body"]["state"] == "stopped"
    assert gateway._Handler.live_screen_scheduler.active.get((session_id, OWNER)) is not True

    h, sent = _handler(tmp_path, b"{}")
    h.owner_ref = OTHER_OWNER
    live_screen_post(h, f"/api/live-screen/sessions/{session_id}/stop",
                     now_ns=1_400_000_000)
    assert sent["code"] == 403

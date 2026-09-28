from harness import gateway
from harness.live_screen_gateway_mount import live_screen_get, live_screen_post
from tests.test_live_screen_gateway_mount import (
    OWNER,
    _approved_final,
    _handler,
    _journey,
    _manager,
    _open_operation,
)


def test_owner_can_recover_lost_open_response_by_body_session_ref_without_capture(tmp_path):
    _journey(tmp_path)
    gateway._Handler.live_screen_manager = _manager()
    gateway._Handler.live_screen_scheduler = None
    gateway._Handler._live_screen_state_root = tmp_path / "state"

    raw = _approved_final(tmp_path, _open_operation(), "open-1")
    h, sent = _handler(tmp_path, raw)
    live_screen_post(h, "/api/live-screen/sessions", now_ns=1_100_000_000)
    assert sent["code"] == 200
    session_id = sent["body"]["session_id"]
    manager = gateway._Handler.live_screen_manager
    assert manager.latest_frame(session_id, "display:primary", owner_ref=OWNER,
                                now_ns=1_150_000_000) is None

    h, sent = _handler(tmp_path)
    h.path = "/api/live-screen/sessions?body_session_ref=body-session-1"
    live_screen_get(h, "/api/live-screen/sessions", now_ns=1_150_000_000)

    assert sent["code"] == 200
    assert sent["body"]["schema"] == "flywheel.live-screen-session-list/v1"
    assert sent["body"]["count"] == 1
    row = sent["body"]["sessions"][0]
    assert row["session_id"] == session_id
    assert row["state"] == "created"
    assert row["source_ids"] == ["display:primary"]
    assert row["destination"] == "openai_responses:vision"
    assert row["model"] == "gpt-6-astra"
    assert row["body_binding"] == {
        "session_ref": "body-session-1", "instrument_ref": "instrument-1"}
    assert row["frames"] == {}
    assert manager.latest_frame(session_id, "display:primary", owner_ref=OWNER,
                                now_ns=1_200_000_000) is None

    h, sent = _handler(tmp_path)
    h.path = "/api/live-screen/sessions?body_session_ref=body-session-1"
    h.owner_ref = "owner_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    live_screen_get(h, "/api/live-screen/sessions", now_ns=1_200_000_000)
    assert sent["code"] == 200
    assert sent["body"]["sessions"] == []

import json

from harness.live_screen_feed import LiveScreenManager, ScreenShareGrant, SourceDescriptor, SyntheticCaptureSource
from harness.live_screen_route import (
    handle_live_screen_get,
    handle_live_screen_post,
    handle_live_screen_preview_get,
)


def _setup():
    manager = LiveScreenManager(clock_ns=lambda: 10_000_000_000,
                                utc_clock=lambda: "2026-09-15T12:00:10Z")
    manager.register_source(
        SourceDescriptor("display:primary", "display", "Primary display",
                         bounds=(0, 0, 100, 80), backend="synthetic"),
        lambda: SyntheticCaptureSource("display:primary", [b"frame-a"], width=100, height=80),
    )
    grant = ScreenShareGrant("owner-A", "openai_responses:vision", "gpt-6-astra",
                             ("display:primary",), 20_000_000_000)
    return manager, grant


def test_route_module_exposes_sources_and_session_lifecycle_for_gateway_owner_hook():
    manager, grant = _setup()
    body, status = handle_live_screen_get("/api/live-screen/sources", manager=manager,
                                          owner_ref="owner-A")
    assert status == 200
    assert body["sources"][0]["source_id"] == "display:primary"

    raw = json.dumps({"sources": [{"source_id": "display:primary"}],
                      "destination": "openai_responses:vision", "model": "gpt-6-astra",
                      "delivery_mode": "sampled_image"}).encode("utf-8")
    session, status = handle_live_screen_post("/api/live-screen/sessions", raw, manager=manager,
                                              grant=grant, owner_ref="owner-A",
                                              now_ns=10_100_000_000)
    assert status == 200
    assert session["state"] == "created"

    start, status = handle_live_screen_post(f"/api/live-screen/sessions/{session['session_id']}/start",
                                            b"{}", manager=manager, grant=grant,
                                            owner_ref="owner-A", now_ns=10_200_000_000)
    assert status == 200 and start["state"] == "active"
    frames, status = handle_live_screen_post(f"/api/live-screen/sessions/{session['session_id']}/poll",
                                             b"{}", manager=manager, grant=grant,
                                             owner_ref="owner-A", now_ns=10_300_000_000)
    assert status == 200
    assert frames["events"] == []
    manager.producer_tick(session["session_id"], owner_ref="owner-A", now_ns=10_300_000_000)
    frames, status = handle_live_screen_post(f"/api/live-screen/sessions/{session['session_id']}/poll",
                                             b"{}", manager=manager, grant=grant,
                                             owner_ref="owner-A", now_ns=10_310_000_000)
    assert status == 200
    assert frames["events"][0]["frame_sha256"]
    drained, status = handle_live_screen_post(f"/api/live-screen/sessions/{session['session_id']}/poll",
                                              b"{}", manager=manager, grant=grant,
                                              owner_ref="owner-A", now_ns=10_320_000_000)
    assert status == 200 and drained["events"] == []
    meta, preview, status = handle_live_screen_preview_get(
        f"/api/live-screen/sessions/{session['session_id']}/sources/display:primary/frames/1/preview",
        manager=manager, owner_ref="owner-A")
    assert status == 200
    assert preview == b"frame-a"
    assert meta["frame"] == frames["events"][0]["frame"]
    assert meta["media_type"] == "image/png"

    stopped, status = handle_live_screen_post(f"/api/live-screen/sessions/{session['session_id']}/stop",
                                              b"{}", manager=manager, grant=grant,
                                              owner_ref="owner-A", now_ns=10_400_000_000)
    assert status == 200
    assert stopped["state"] == "stopped"


def test_route_rejects_unknown_paths_and_malformed_json_cleanly():
    manager, grant = _setup()
    body, status = handle_live_screen_get("/api/live-screen/nope", manager=manager,
                                          owner_ref="owner-A")
    assert status == 404 and body["error"]["code"] == "NOT_FOUND"

    body, status = handle_live_screen_post("/api/live-screen/sessions", b"{", manager=manager,
                                           grant=grant, owner_ref="owner-A", now_ns=10_100_000_000)
    assert status == 400 and body["error"]["code"] == "MALFORMED_JSON"

"""Live-screen app flow through the real gateway HTTP handler."""

from __future__ import annotations

import json

import pytest

from tests.app_live_screen_http_fixture import (
    BODY_SESSION,
    DeterministicScheduler,
    INSTRUMENT,
    OTHER_OWNER,
    OWNER,
    SOURCE,
    TOKEN,
    LiveGateway,
    approve_final,
    create_journey,
    live_manager,
    open_operation,
)


@pytest.fixture
def live_gateways(tmp_path):
    manager = live_manager()
    scheduler = DeterministicScheduler(manager, tick_interval_ms=60_000)
    owner = other = None
    try:
        owner = LiveGateway(
            tmp_path / "owner-a",
            owner_ref=OWNER,
            manager=manager,
            scheduler=scheduler,
        )
        other = LiveGateway(
            tmp_path / "owner-b",
            owner_ref=OTHER_OWNER,
            manager=manager,
            scheduler=scheduler,
        )
        yield owner, other, manager, scheduler
    finally:
        if owner is not None:
            owner.close()
        if other is not None:
            other.close()


def test_private_live_screen_http_requires_bearer_custody(live_gateways):
    owner, _, _, _ = live_gateways

    missing_status, missing = owner.request(
        "/api/live-screen/status",
        token=None,
    )
    wrong_status, wrong = owner.request(
        "/api/live-screen/status",
        token="wrong-token",
    )
    bad_host_status, bad_host = owner.request(
        "/api/live-screen/status",
        host="attacker.invalid",
    )

    assert missing_status == wrong_status == bad_host_status == 401
    assert missing["error"]["code"] == "AUTH_REQUIRED"
    assert wrong["error"]["code"] == "AUTH_REQUIRED"
    assert bad_host["error"]["code"] == "AUTH_REQUIRED"
    assert TOKEN not in json.dumps([missing, wrong, bad_host])


def test_live_screen_http_open_recovery_owner_isolation_and_empty_stop(
    live_gateways,
):
    owner, other, manager, scheduler = live_gateways
    create_journey(owner.home)

    final = approve_final(owner, open_operation(), "open-live-screen-1")
    status, opened = owner.request("/api/live-screen/sessions", final)
    assert status == 200, opened
    assert opened["state"] == "active"
    assert opened["body_binding"] == {
        "session_ref": BODY_SESSION,
        "instrument_ref": INSTRUMENT,
    }
    assert opened["producer"]["tick_events"] == 1
    assert opened["authority"]["action"] == "live_screen.control"
    session_id = opened["session_id"]

    status, recovery = owner.request(
        f"/api/live-screen/sessions?body_session_ref={BODY_SESSION}",
    )
    assert status == 200, recovery
    assert recovery["count"] == 1
    assert recovery["sessions"][0]["session_id"] == session_id
    assert recovery["sessions"][0]["body_binding"] == opened["body_binding"]

    other_status, other_recovery = other.request(
        f"/api/live-screen/sessions?body_session_ref={BODY_SESSION}",
    )
    assert other_status == 200
    assert other_recovery["sessions"] == []

    read_status, read_denial = other.request(
        f"/api/live-screen/sessions/{session_id}",
    )
    stop_status, stop_denial = other.request(
        f"/api/live-screen/sessions/{session_id}/stop",
        {},
    )
    assert read_status == stop_status == 403
    assert read_denial["error"]["code"] == "OWNER_NOT_AUTHORIZED"
    assert stop_denial["error"]["code"] == "OWNER_NOT_AUTHORIZED"

    poll_status, poll = owner.request(
        f"/api/live-screen/sessions/{session_id}/poll",
        {},
    )
    assert poll_status == 200
    assert [event["source_sequence"] for event in poll["events"]] == [1]
    state_status, active_state = owner.request(
        f"/api/live-screen/sessions/{session_id}",
    )
    assert state_status == 200
    assert active_state["frames"] == {SOURCE: 1}

    status, stopped = owner.request(
        f"/api/live-screen/sessions/{session_id}/stop",
        {},
    )
    assert status == 200
    assert stopped["state"] == "stopped"
    assert scheduler.active.get((session_id, OWNER)) is not True
    before = manager._sessions[session_id].source_sequences[SOURCE]
    scheduler.tick_all()
    after = manager._sessions[session_id].source_sequences[SOURCE]
    assert after == before == 1

    status, post_stop_poll = owner.request(
        f"/api/live-screen/sessions/{session_id}/poll",
        {},
    )
    assert status == 200
    assert post_stop_poll["events"] == []


def test_empty_live_screen_open_resume_and_deliver_do_not_bypass_grants(
    live_gateways,
):
    owner, _, _, _ = live_gateways
    create_journey(owner.home)
    final = approve_final(owner, open_operation(), "open-live-screen-2")
    status, opened = owner.request("/api/live-screen/sessions", final)
    assert status == 200, opened
    session_id = opened["session_id"]

    open_status, open_denial = owner.request("/api/live-screen/sessions", {})
    pause_status, paused = owner.request(
        f"/api/live-screen/sessions/{session_id}/pause",
        {},
    )
    resume_status, resume_denial = owner.request(
        f"/api/live-screen/sessions/{session_id}/resume",
        {},
    )
    deliver_status, deliver_denial = owner.request(
        f"/api/live-screen/sessions/{session_id}/sources/display%3Aprimary/deliver",
        {},
    )
    state_status, state = owner.request(f"/api/live-screen/sessions/{session_id}")

    assert open_status == resume_status == deliver_status == 422
    assert open_denial["error"]["code"] == "INVALID_REQUEST"
    assert resume_denial["error"]["code"] == "INVALID_REQUEST"
    assert deliver_denial["error"]["code"] == "INVALID_REQUEST"
    assert pause_status == 200
    assert paused["state"] == "paused"
    assert state_status == 200
    assert state["state"] == "paused"
    assert state["frames"] == {SOURCE: 1}

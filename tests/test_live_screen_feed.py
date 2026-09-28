import pytest

from harness.live_screen_feed import (
    LiveScreenError,
    LiveScreenManager,
    ScreenShareGrant,
    SourceDescriptor,
    SyntheticCaptureSource,
)


def _manager():
    manager = LiveScreenManager(clock_ns=lambda: 1_000_000_000,
                                utc_clock=lambda: "2026-09-15T12:00:00Z")
    manager.register_source(
        SourceDescriptor("display:primary", "display", "Primary display",
                         bounds=(0, 0, 640, 480), backend="synthetic"),
        lambda: SyntheticCaptureSource("display:primary", [b"display-a", b"display-b"],
                                       width=640, height=480),
    )
    manager.register_source(
        SourceDescriptor("window:editor", "window", "Editor window",
                         bounds=(20, 30, 320, 200), backend="synthetic"),
        lambda: SyntheticCaptureSource("window:editor", [b"window-a", b"window-b"],
                                       width=320, height=200),
    )
    return manager


def _grant(*, source_ids=("display:primary", "window:editor"), expires=5_000_000_000):
    return ScreenShareGrant(owner_ref="owner-A", destination="openai_responses:vision",
                            model="gpt-6-astra", source_ids=source_ids,
                            expires_at_ns=expires)


def test_plural_session_records_frame_identity_and_bounds_buffers():
    manager = _manager()
    session = manager.open_session({
        "sources": [{"source_id": "display:primary"}, {"source_id": "window:editor"}],
        "destination": "openai_responses:vision",
        "model": "gpt-6-astra",
        "delivery_mode": "sampled_image",
        "buffer_frames_per_source": 1,
        "max_frame_bytes": 64,
    }, grant=_grant(), owner_ref="owner-A", now_ns=1_100_000_000)

    assert session["state"] == "created"
    assert manager.session_status(session["session_id"], owner_ref="owner-A")["frames"] == {}

    manager.start_session(session["session_id"], owner_ref="owner-A", now_ns=1_200_000_000)
    first_events = manager.producer_tick(
        session["session_id"], owner_ref="owner-A", now_ns=1_300_000_000)
    assert [(e["source_id"], e["source_sequence"], e["aggregate_sequence"])
            for e in first_events] == [("display:primary", 1, 1), ("window:editor", 1, 2)]
    assert all(e["event"] == "screen.frame" for e in first_events)
    assert all("payload" not in e and "bytes" not in e for e in first_events)
    assert first_events[0]["frame_sha256"] == manager.latest_frame(
        session["session_id"], "display:primary", owner_ref="owner-A").frame_sha256

    second_events = manager.producer_tick(
        session["session_id"], owner_ref="owner-A", now_ns=1_400_000_000)
    status = manager.session_status(session["session_id"], owner_ref="owner-A")
    assert [(e["source_id"], e["source_sequence"], e["aggregate_sequence"])
            for e in second_events] == [("display:primary", 2, 3), ("window:editor", 2, 4)]
    assert status["dropped_frames"] == {"display:primary": 1, "window:editor": 1}
    assert status["frames"] == {"display:primary": 2, "window:editor": 2}


def test_session_authority_binds_sources_destination_model_and_expiration():
    manager = _manager()
    with pytest.raises(LiveScreenError) as malformed_err:
        manager.open_session([], grant=_grant(), owner_ref="owner-A", now_ns=1_100_000_000)
    assert malformed_err.value.code == "INVALID_REQUEST"

    with pytest.raises(LiveScreenError) as source_err:
        manager.open_session({"sources": [{"source_id": "window:editor"}],
                              "destination": "openai_responses:vision", "model": "gpt-6-astra",
                              "delivery_mode": "sampled_image"},
                             grant=_grant(source_ids=("display:primary",)), owner_ref="owner-A",
                             now_ns=1_100_000_000)
    assert source_err.value.code == "SOURCE_NOT_AUTHORIZED"

    with pytest.raises(LiveScreenError) as dest_err:
        manager.open_session({"sources": [{"source_id": "display:primary"}],
                              "destination": "openai_responses:other", "model": "gpt-6-astra",
                              "delivery_mode": "sampled_image"},
                             grant=_grant(source_ids=("display:primary",)), owner_ref="owner-A",
                             now_ns=1_100_000_000)
    assert dest_err.value.code == "DESTINATION_NOT_AUTHORIZED"

    with pytest.raises(LiveScreenError) as model_err:
        manager.open_session({"sources": [{"source_id": "display:primary"}],
                              "destination": "openai_responses:vision", "model": "text-only",
                              "delivery_mode": "sampled_image"},
                             grant=_grant(source_ids=("display:primary",)), owner_ref="owner-A",
                             now_ns=1_100_000_000)
    assert model_err.value.code == "MODEL_NOT_AUTHORIZED"

    with pytest.raises(LiveScreenError) as expired_err:
        manager.open_session({"sources": [{"source_id": "display:primary"}],
                              "destination": "openai_responses:vision", "model": "gpt-6-astra",
                              "delivery_mode": "sampled_image"},
                             grant=_grant(source_ids=("display:primary",), expires=1_100_000_000),
                             owner_ref="owner-A", now_ns=1_100_000_000)
    assert expired_err.value.code == "SCREEN_SHARE_EXPIRED"


def test_provider_model_ref_allows_slash_but_source_refs_remain_strict():
    manager = _manager()
    grant = ScreenShareGrant("owner-A", "openai_responses:vision", "org/model-vision:1",
                             ("display:primary",), 5_000_000_000)
    session = manager.open_session({"sources": [{"source_id": "display:primary"}],
                                    "destination": "openai_responses:vision",
                                    "model": "org/model-vision:1",
                                    "delivery_mode": "sampled_image"},
                                   grant=grant, owner_ref="owner-A", now_ns=1_100_000_000)
    assert session["model"] == "org/model-vision:1"

    with pytest.raises(LiveScreenError) as source_err:
        manager.open_session({"sources": [{"source_id": "display/primary"}],
                              "destination": "openai_responses:vision",
                              "model": "org/model-vision:1",
                              "delivery_mode": "sampled_image"},
                             grant=grant, owner_ref="owner-A", now_ns=1_100_000_000)
    assert source_err.value.code == "INVALID_ID"


def test_manager_total_buffer_budget_spans_concurrent_sessions():
    manager = LiveScreenManager(max_total_buffer_bytes=80)
    for sid in ("display:primary", "window:editor"):
        manager.register_source(
            SourceDescriptor(sid, "display", sid, bounds=(0, 0, 10, 10), backend="synthetic"),
            lambda sid=sid: SyntheticCaptureSource(sid, [b"x"], width=10, height=10),
        )
    grant = _grant(source_ids=("display:primary", "window:editor"))
    manager.open_session({"sources": [{"source_id": "display:primary"}],
                          "destination": "openai_responses:vision", "model": "gpt-6-astra",
                          "delivery_mode": "sampled_image", "buffer_frames_per_source": 1,
                          "max_frame_bytes": 64},
                         grant=grant, owner_ref="owner-A", now_ns=1_100_000_000)
    with pytest.raises(LiveScreenError) as budget_err:
        manager.open_session({"sources": [{"source_id": "window:editor"}],
                              "destination": "openai_responses:vision", "model": "gpt-6-astra",
                              "delivery_mode": "sampled_image", "buffer_frames_per_source": 1,
                              "max_frame_bytes": 64},
                             grant=grant, owner_ref="owner-A", now_ns=1_200_000_000)
    assert budget_err.value.code == "BUFFER_BUDGET_EXCEEDED"


def test_pause_and_stop_prevent_new_or_delayed_frames():
    manager = _manager()
    session = manager.open_session({"sources": [{"source_id": "display:primary"}],
                                    "destination": "openai_responses:vision", "model": "gpt-6-astra",
                                    "delivery_mode": "sampled_image"},
                                   grant=_grant(source_ids=("display:primary",)), owner_ref="owner-A",
                                   now_ns=1_100_000_000)
    manager.start_session(session["session_id"], owner_ref="owner-A", now_ns=1_200_000_000)
    manager.producer_tick(session["session_id"], owner_ref="owner-A", now_ns=1_300_000_000)

    manager.pause_session(session["session_id"], owner_ref="owner-A", now_ns=1_350_000_000)
    assert manager.producer_tick(session["session_id"], owner_ref="owner-A",
                                 now_ns=1_360_000_000) == []
    with pytest.raises(LiveScreenError) as owner_err:
        manager.session_status(session["session_id"], owner_ref="owner-B")
    assert owner_err.value.code == "OWNER_NOT_AUTHORIZED"

    manager.resume_session(session["session_id"], owner_ref="owner-A", now_ns=1_370_000_000)
    manager.stop_session(session["session_id"], owner_ref="owner-A", now_ns=1_380_000_000)
    assert manager.session_status(session["session_id"], owner_ref="owner-A")["state"] == "stopped"
    assert manager.latest_frame(session["session_id"], "display:primary", owner_ref="owner-A") is None
    with pytest.raises(LiveScreenError) as stopped_err:
        manager.frame_for_delivery(session["session_id"], "display:primary", owner_ref="owner-A",
                                   grant=_grant(source_ids=("display:primary",)),
                                   destination="openai_responses:vision", model="gpt-6-astra",
                                   now_ns=1_390_000_000)
    assert stopped_err.value.code == "SESSION_STOPPED"


def test_status_preview_and_delivery_require_unexpired_original_binding():
    manager = _manager()
    grant = _grant(source_ids=("display:primary",), expires=1_500_000_000)
    session = manager.open_session({"sources": [{"source_id": "display:primary"}],
                                    "destination": "openai_responses:vision", "model": "gpt-6-astra",
                                    "delivery_mode": "sampled_image"},
                                   grant=grant, owner_ref="owner-A", now_ns=1_100_000_000)
    manager.start_session(session["session_id"], owner_ref="owner-A", now_ns=1_200_000_000)
    manager.producer_tick(session["session_id"], owner_ref="owner-A", now_ns=1_300_000_000)
    newer_grant = ScreenShareGrant("owner-A", "openai_responses:other", "gpt-6-astra",
                                   ("display:primary",), 5_000_000_000)

    with pytest.raises(LiveScreenError) as binding_err:
        manager.frame_for_delivery(session["session_id"], "display:primary", owner_ref="owner-A",
                                   grant=newer_grant, destination="openai_responses:other",
                                   model="gpt-6-astra", now_ns=1_400_000_000)
    assert binding_err.value.code == "SESSION_DESTINATION_MISMATCH"

    with pytest.raises(LiveScreenError) as status_err:
        manager.session_status(session["session_id"], owner_ref="owner-A", now_ns=1_500_000_000)
    assert status_err.value.code == "SCREEN_SHARE_EXPIRED"
    with pytest.raises(LiveScreenError) as preview_err:
        manager.preview_frame(session["session_id"], "display:primary", 1,
                              owner_ref="owner-A", now_ns=1_500_000_000)
    assert preview_err.value.code == "SCREEN_SHARE_EXPIRED"

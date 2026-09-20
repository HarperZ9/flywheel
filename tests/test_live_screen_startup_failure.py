import pytest

from harness import gateway
from harness.live_screen_feed import LiveScreenError, LiveScreenManager, SourceDescriptor
from harness.live_screen_gateway_mount import live_screen_post
from harness.live_screen_types import ScreenShareGrant
from tests.test_live_screen_gateway_mount import (
    _approved_final,
    _handler,
    _journey,
    _open_operation,
)


OWNER = "owner_" + "a" * 32


class _ClosableSource:
    def __init__(self, log, source_id):
        self.log = log
        self.source_id = source_id

    def frames(self):
        return iter(())

    def close(self):
        self.log.append(("closed", self.source_id))


class _FramesRaiseSource(_ClosableSource):
    def frames(self):
        raise RuntimeError("frames iterator failed")


def _register(manager, source_id, factory):
    manager.register_source(
        SourceDescriptor(source_id, "display", source_id, bounds=(0, 0, 2, 2),
                         backend="synthetic"),
        factory,
    )


def test_atomic_open_start_cleans_ordinary_source_start_failure(tmp_path):
    _journey(tmp_path)
    manager = LiveScreenManager(clock_ns=lambda: 1_000_000_000)
    _register(manager, "display:primary",
              lambda: (_ for _ in ()).throw(RuntimeError("native source open failed")))
    gateway._Handler.live_screen_manager = manager
    gateway._Handler.live_screen_scheduler = None
    gateway._Handler._live_screen_state_root = tmp_path / "state"
    raw = _approved_final(
        tmp_path, {**_open_operation(), "start_immediately": True},
        "open-start-fails")
    h, sent = _handler(tmp_path, raw)

    live_screen_post(h, "/api/live-screen/sessions", now_ns=1_100_000_000)

    assert sent["code"] == 400
    assert sent["body"]["error"]["code"] == "SOURCE_START_FAILED"
    assert manager._reserved_buffer_bytes == 0
    sessions = list(manager._sessions.values())
    assert len(sessions) == 1
    assert sessions[0].state == "stopped"
    assert sessions[0].reserved_buffer_bytes == 0
    assert sessions[0].capture_sources == {}
    assert sessions[0].iterators == {}


def test_direct_start_closes_partial_multisource_resources_on_factory_failure():
    log = []
    manager = LiveScreenManager(max_total_buffer_bytes=128, clock_ns=lambda: 1_000_000_000)
    _register(manager, "display:primary", lambda: _ClosableSource(log, "display:primary"))
    _register(manager, "display:secondary",
              lambda: (_ for _ in ()).throw(OSError("second source failed")))
    grant = ScreenShareGrant("owner-A", "openai_responses:vision", "gpt-6-astra",
                             ("display:primary", "display:secondary"), 5_000_000_000)
    session = manager.open_session({
        "sources": [{"source_id": "display:primary"}, {"source_id": "display:secondary"}],
        "destination": "openai_responses:vision",
        "model": "gpt-6-astra",
        "delivery_mode": "sampled_image",
        "buffer_frames_per_source": 1,
        "max_frame_bytes": 64,
    }, grant=grant, owner_ref="owner-A", now_ns=1_100_000_000)

    with pytest.raises(LiveScreenError) as err:
        manager.start_session(session["session_id"], owner_ref="owner-A",
                              now_ns=1_200_000_000)

    raw = manager._sessions[session["session_id"]]
    assert err.value.code == "SOURCE_START_FAILED"
    assert manager._reserved_buffer_bytes == 0
    assert raw.state == "stopped"
    assert raw.reserved_buffer_bytes == 0
    assert raw.capture_sources == {}
    assert raw.iterators == {}
    assert log == [("closed", "display:primary")]


def test_direct_start_closes_source_when_frames_method_raises():
    log = []
    manager = LiveScreenManager(max_total_buffer_bytes=64, clock_ns=lambda: 1_000_000_000)
    _register(manager, "display:primary",
              lambda: _FramesRaiseSource(log, "display:primary"))
    grant = ScreenShareGrant("owner-A", "openai_responses:vision", "gpt-6-astra",
                             ("display:primary",), 5_000_000_000)
    session = manager.open_session({
        "sources": [{"source_id": "display:primary"}],
        "destination": "openai_responses:vision",
        "model": "gpt-6-astra",
        "delivery_mode": "sampled_image",
        "buffer_frames_per_source": 1,
        "max_frame_bytes": 64,
    }, grant=grant, owner_ref="owner-A", now_ns=1_100_000_000)

    with pytest.raises(LiveScreenError) as err:
        manager.start_session(session["session_id"], owner_ref="owner-A",
                              now_ns=1_200_000_000)

    raw = manager._sessions[session["session_id"]]
    assert err.value.code == "SOURCE_START_FAILED"
    assert manager._reserved_buffer_bytes == 0
    assert raw.state == "stopped"
    assert raw.capture_sources == {}
    assert raw.iterators == {}
    assert log == [("closed", "display:primary")]

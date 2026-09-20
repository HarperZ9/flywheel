from types import SimpleNamespace

import pytest

from harness.live_screen_delivery import DeliveryError, deliver_latest_sampled_image
from harness.live_screen_feed import LiveScreenError, LiveScreenManager
from harness.live_screen_types import ScreenShareGrant, SourceDescriptor, SyntheticCaptureSource


class _ClosableFrame:
    def __init__(self, source_id="display:primary"):
        self.descriptor = SimpleNamespace(width=10, height=10, pixel_format="png",
                                          timestamp="2026-09-15T12:00:00Z")
        self.media_type = "image/png"
        self._payload = f"{source_id}:frame".encode("utf-8")

    def read(self):
        return self._payload


class _ClosableIterator:
    def __init__(self, log, source_id="display:primary", *, fail_close=False):
        self._log = log
        self._source_id = source_id
        self._fail_close = fail_close
        self._sent = False

    def __iter__(self):
        return self

    def __next__(self):
        if self._sent:
            raise StopIteration
        self._sent = True
        return _ClosableFrame(self._source_id)

    def close(self):
        self._log.append(("iterator", self._source_id))
        if self._fail_close:
            raise RuntimeError("iterator close failed")


class _ClosableSource:
    def __init__(self, log, source_id="display:primary", *, fail_close=False):
        self._log = log
        self._source_id = source_id
        self._fail_close = fail_close

    def frames(self):
        return _ClosableIterator(self._log, self._source_id, fail_close=self._fail_close)

    def close(self):
        self._log.append(("source", self._source_id))
        if self._fail_close:
            raise RuntimeError("source close failed")


def _grant(*, source_ids=("display:primary",), expires=5_000_000_000):
    return ScreenShareGrant("owner-A", "openai_responses:vision", "gpt-6-astra",
                            source_ids, expires)


def _one_source_manager(*, max_total_buffer_bytes=64 << 20, factory=None):
    manager = LiveScreenManager(max_total_buffer_bytes=max_total_buffer_bytes)
    manager.register_source(
        SourceDescriptor("display:primary", "display", "Primary display",
                         bounds=(0, 0, 10, 10), backend="synthetic"),
        factory or (lambda: SyntheticCaptureSource("display:primary", [b"x"],
                                                   width=10, height=10)),
    )
    return manager


def test_expired_session_releases_budget_and_clears_preview_without_explicit_stop():
    manager = _one_source_manager(max_total_buffer_bytes=64)
    session = manager.open_session({"sources": [{"source_id": "display:primary"}],
                                    "destination": "openai_responses:vision",
                                    "model": "gpt-6-astra", "delivery_mode": "sampled_image",
                                    "buffer_frames_per_source": 1, "max_frame_bytes": 64},
                                   grant=_grant(expires=1_500_000_000),
                                   owner_ref="owner-A", now_ns=1_100_000_000)
    manager.start_session(session["session_id"], owner_ref="owner-A", now_ns=1_200_000_000)
    manager.producer_tick(session["session_id"], owner_ref="owner-A", now_ns=1_300_000_000)

    with pytest.raises(LiveScreenError) as expired_err:
        manager.session_status(session["session_id"], owner_ref="owner-A", now_ns=1_500_000_000)
    assert expired_err.value.code == "SCREEN_SHARE_EXPIRED"
    assert manager.session_status(session["session_id"], owner_ref="owner-A")["state"] == "stopped"
    assert manager.latest_frame(session["session_id"], "display:primary", owner_ref="owner-A") is None

    fresh = manager.open_session({"sources": [{"source_id": "display:primary"}],
                                  "destination": "openai_responses:vision",
                                  "model": "gpt-6-astra", "delivery_mode": "sampled_image",
                                  "buffer_frames_per_source": 1, "max_frame_bytes": 64},
                                 grant=_grant(expires=3_000_000_000),
                                 owner_ref="owner-A", now_ns=1_600_000_000)
    assert fresh["state"] == "created"


def test_stop_closes_owned_source_and_iterator_resources():
    log = []
    manager = _one_source_manager(factory=lambda: _ClosableSource(log))
    session = manager.open_session({"sources": [{"source_id": "display:primary"}],
                                    "destination": "openai_responses:vision",
                                    "model": "gpt-6-astra", "delivery_mode": "sampled_image"},
                                   grant=_grant(), owner_ref="owner-A", now_ns=1_100_000_000)
    manager.start_session(session["session_id"], owner_ref="owner-A", now_ns=1_200_000_000)
    manager.producer_tick(session["session_id"], owner_ref="owner-A", now_ns=1_300_000_000)

    manager.stop_session(session["session_id"], owner_ref="owner-A", now_ns=1_400_000_000)

    assert log == [("iterator", "display:primary"), ("source", "display:primary")]


def test_expiry_cleanup_surfaces_bounded_close_failures():
    log = []
    manager = _one_source_manager(max_total_buffer_bytes=64,
                                  factory=lambda: _ClosableSource(log, fail_close=True))
    session = manager.open_session({"sources": [{"source_id": "display:primary"}],
                                    "destination": "openai_responses:vision",
                                    "model": "gpt-6-astra", "delivery_mode": "sampled_image",
                                    "buffer_frames_per_source": 1, "max_frame_bytes": 64},
                                   grant=_grant(expires=1_500_000_000),
                                   owner_ref="owner-A", now_ns=1_100_000_000)
    manager.start_session(session["session_id"], owner_ref="owner-A", now_ns=1_200_000_000)

    with pytest.raises(LiveScreenError) as expired_err:
        manager.producer_tick(session["session_id"], owner_ref="owner-A", now_ns=1_500_000_000)

    assert expired_err.value.code == "SCREEN_SHARE_EXPIRED"
    assert "cleanup failed" in str(expired_err.value)
    status = manager.session_status(session["session_id"], owner_ref="owner-A")
    assert status["state"] == "stopped"
    assert status["cleanup_errors"] == [
        "display:primary iterator close RuntimeError: iterator close failed",
        "display:primary source close RuntimeError: source close failed",
    ]
    fresh = manager.open_session({"sources": [{"source_id": "display:primary"}],
                                  "destination": "openai_responses:vision",
                                  "model": "gpt-6-astra", "delivery_mode": "sampled_image",
                                  "buffer_frames_per_source": 1, "max_frame_bytes": 64},
                                 grant=_grant(expires=3_000_000_000),
                                 owner_ref="owner-A", now_ns=1_600_000_000)
    assert fresh["state"] == "created"


def test_pending_delivery_expiry_cleans_session_before_error_returns():
    log = []
    manager = _one_source_manager(max_total_buffer_bytes=64, factory=lambda: _ClosableSource(log))
    grant = _grant(expires=2_500_000_000)
    session = manager.open_session({"sources": [{"source_id": "display:primary"}],
                                    "destination": "openai_responses:vision",
                                    "model": "gpt-6-astra", "delivery_mode": "sampled_image",
                                    "buffer_frames_per_source": 1, "max_frame_bytes": 64},
                                   grant=grant, owner_ref="owner-A", now_ns=2_000_000_000)
    session_id = session["session_id"]
    manager.start_session(session_id, owner_ref="owner-A", now_ns=2_100_000_000)
    manager.producer_tick(session_id, owner_ref="owner-A", now_ns=2_200_000_000)

    class SentTransport:
        model = "gpt-6-astra"
        model_route = "openai_responses:vision"

        def __init__(self):
            self.sent = False

        def send_sampled_image(self, *, frame, prompt, timeout=30.0):
            self.sent = True
            return {"provider_status": 200, "provider_response_id": "late"}

    transport = SentTransport()
    with pytest.raises(DeliveryError) as err:
        deliver_latest_sampled_image(
            manager, session_id=session_id, source_id="display:primary", owner_ref="owner-A",
            grant=grant, destination="openai_responses:vision", model="gpt-6-astra",
            prompt="Describe it.", transport=transport, now_ns=2_300_000_000,
            clock_ns=lambda: 2_500_000_000,
            utc_now=lambda: "2026-09-15T12:00:02Z")

    raw_session = manager._sessions[session_id]
    assert transport.sent is True
    assert err.value.code == "SCREEN_SHARE_EXPIRED"
    assert raw_session.state == "stopped"
    assert raw_session.reserved_buffer_bytes == 0
    assert manager._reserved_buffer_bytes == 0
    assert raw_session.capture_sources == {}
    assert raw_session.iterators == {}
    assert list(raw_session.buffers["display:primary"]) == []
    assert log == [("iterator", "display:primary"), ("source", "display:primary")]

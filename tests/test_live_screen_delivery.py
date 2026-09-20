import base64
import json

import pytest

from harness.gateway_agent_transport import BoundAgentTransport
from harness.live_screen_delivery import (
    DeliveryError,
    OpenAIResponsesImageTransport,
    deliver_latest_sampled_image,
    deliver_native_video,
    verify_body_action_frame_reference,
)
from harness.live_screen_feed import (
    LiveScreenManager,
    ScreenShareGrant,
    SourceDescriptor,
    SyntheticCaptureSource,
)


class _FakeResponse:
    status = 200
    fp = None

    def __init__(self, body):
        self._body = json.dumps(body).encode("utf-8")
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
        return _FakeResponse({"id": "resp_live_1", "output": []})


def _prepared_manager():
    manager = LiveScreenManager(clock_ns=lambda: 2_000_000_000,
                                utc_clock=lambda: "2026-09-15T12:00:02Z")
    manager.register_source(
        SourceDescriptor("display:primary", "display", "Primary display",
                         bounds=(0, 0, 2, 2), backend="synthetic"),
        lambda: SyntheticCaptureSource("display:primary", [b"\x89PNG\r\nlive-bytes"],
                                       width=2, height=2, media_type="image/png"),
    )
    grant = ScreenShareGrant("owner-A", "openai_responses:vision", "gpt-6-astra",
                             ("display:primary",), 50_000_000_000)
    session = manager.open_session({"sources": [{"source_id": "display:primary"}],
                                    "destination": "openai_responses:vision", "model": "gpt-6-astra",
                                    "delivery_mode": "sampled_image"},
                                   grant=grant, owner_ref="owner-A", now_ns=2_000_000_000)
    manager.start_session(session["session_id"], owner_ref="owner-A", now_ns=2_100_000_000)
    manager.producer_tick(session["session_id"], owner_ref="owner-A", now_ns=2_200_000_000)
    return manager, session["session_id"], grant


def test_sampled_image_delivery_sends_real_frame_bytes_through_openai_responses_transport():
    manager, session_id, grant = _prepared_manager()
    opener = _FakeOpener()
    bound = BoundAgentTransport(base_url="https://api.openai.com/v1", adapter="openai",
                                model="gpt-6-astra", deadline=100.0, max_tokens=64,
                                max_calls=1, clock=lambda: 0.0, opener=opener,
                                native_protocol="openai_responses")
    transport = OpenAIResponsesImageTransport(bound, base_url="https://api.openai.com/v1",
                                              model="gpt-6-astra", api_key="sk-test",
                                              max_output_tokens=64,
                                              model_route="openai_responses:vision")

    receipt = deliver_latest_sampled_image(
        manager, session_id=session_id, source_id="display:primary", owner_ref="owner-A",
        grant=grant, destination="openai_responses:vision", model="gpt-6-astra",
        prompt="Describe the selected live screen frame.", transport=transport,
        now_ns=2_300_000_000, clock_ns=lambda: 32_300_000_000,
        utc_now=lambda: "2026-09-15T12:00:33Z")

    request, timeout = opener.requests[0]
    assert timeout == 30.0
    payload = json.loads(request.data.decode("utf-8"))
    content = payload["input"][0]["content"]
    image_part = next(part for part in content if part["type"] == "input_image")
    sent = base64.b64decode(image_part["image_url"].split(",", 1)[1])
    assert sent == b"\x89PNG\r\nlive-bytes"
    assert receipt["event"] == "screen.delivery"
    assert receipt["delivery_mode"] == "sampled_image"
    assert receipt["model_route"] == "openai_responses:vision"
    assert receipt["model"] == "gpt-6-astra"
    assert receipt["frame_age_ms"] == 30_100
    assert receipt["stale"] is False
    assert receipt["provider_response_id"] == "resp_live_1"

    action = {"kind": "studio.body.act", "live_screen_frame": receipt["frame"]}
    assert verify_body_action_frame_reference(action, receipt)["ok"] is True
    wrong = {"kind": "studio.body.act", "live_screen_frame": {**receipt["frame"], "frame_sha256": "0" * 64}}
    assert verify_body_action_frame_reference(wrong, receipt) == {
        "ok": False, "code": "FRAME_REFERENCE_MISMATCH"}


def test_stopped_session_suppresses_outstanding_sampled_image_delivery():
    manager, session_id, grant = _prepared_manager()
    manager.stop_session(session_id, owner_ref="owner-A", now_ns=2_250_000_000)
    opener = _FakeOpener()
    bound = BoundAgentTransport(base_url="https://api.openai.com/v1", adapter="openai",
                                model="gpt-6-astra", deadline=100.0, max_tokens=64,
                                max_calls=1, clock=lambda: 0.0, opener=opener,
                                native_protocol="openai_responses")
    transport = OpenAIResponsesImageTransport(bound, base_url="https://api.openai.com/v1",
                                              model="gpt-6-astra", api_key="sk-test",
                                              max_output_tokens=64,
                                              model_route="openai_responses:vision")

    with pytest.raises(DeliveryError) as err:
        deliver_latest_sampled_image(
            manager, session_id=session_id, source_id="display:primary", owner_ref="owner-A",
            grant=grant, destination="openai_responses:vision", model="gpt-6-astra",
            prompt="Describe it.", transport=transport,
            now_ns=2_300_000_000, utc_now=lambda: "2026-09-15T12:00:03Z")
    assert err.value.code == "SESSION_STOPPED"
    assert opener.requests == []


def test_transport_route_and_model_must_match_session_binding_before_send():
    manager, session_id, grant = _prepared_manager()
    opener = _FakeOpener()
    bound = BoundAgentTransport(base_url="https://api.openai.com/v1", adapter="openai",
                                model="other/model", deadline=100.0, max_tokens=64,
                                max_calls=1, clock=lambda: 0.0, opener=opener,
                                native_protocol="openai_responses")
    transport = OpenAIResponsesImageTransport(bound, base_url="https://api.openai.com/v1",
                                              model="other/model", api_key="sk-test",
                                              max_output_tokens=64,
                                              model_route="openai_responses:vision")
    with pytest.raises(DeliveryError) as err:
        deliver_latest_sampled_image(
            manager, session_id=session_id, source_id="display:primary", owner_ref="owner-A",
            grant=grant, destination="openai_responses:vision", model="gpt-6-astra",
            prompt="Describe it.", transport=transport, now_ns=2_300_000_000,
            utc_now=lambda: "2026-09-15T12:00:03Z")
    assert err.value.code == "TRANSPORT_MODEL_MISMATCH"
    assert opener.requests == []


def test_delivery_rechecks_stop_after_transport_before_success_receipt():
    manager, session_id, grant = _prepared_manager()

    class StoppingTransport:
        model = "gpt-6-astra"
        model_route = "openai_responses:vision"

        def __init__(self):
            self.sent = False

        def send_sampled_image(self, *, frame, prompt, timeout=30.0):
            self.sent = True
            manager.stop_session(session_id, owner_ref="owner-A", now_ns=2_350_000_000)
            return {"provider_status": 200, "provider_response_id": "late"}

    transport = StoppingTransport()
    with pytest.raises(DeliveryError) as err:
        deliver_latest_sampled_image(
            manager, session_id=session_id, source_id="display:primary", owner_ref="owner-A",
            grant=grant, destination="openai_responses:vision", model="gpt-6-astra",
            prompt="Describe it.", transport=transport, now_ns=2_300_000_000,
            clock_ns=lambda: 2_360_000_000,
            utc_now=lambda: "2026-09-15T12:00:03Z")
    assert transport.sent is True
    assert err.value.code == "SESSION_STOPPED"


def test_delivery_rechecks_expiration_after_transport_before_success_receipt():
    manager, session_id, grant = _prepared_manager()

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
            prompt="Describe it.", transport=transport, now_ns=49_900_000_000,
            clock_ns=lambda: 50_000_000_000,
            utc_now=lambda: "2026-09-15T12:00:50Z")
    assert transport.sent is True
    assert err.value.code == "SCREEN_SHARE_EXPIRED"


def test_raw_bgra_frame_is_not_mislabeled_as_sampled_image():
    class RawFrame:
        media_type = None

        def __init__(self):
            self.descriptor = type("Desc", (), {
                "source_id": "display:raw", "width": 1, "height": 1,
                "pixel_format": "bgra", "timestamp": None})()

        def read(self):
            return b"\x00\x01\x02\xff"

    class RawSource:
        def frames(self):
            yield RawFrame()

    manager = LiveScreenManager()
    manager.register_source(SourceDescriptor("display:raw", "display", "Raw",
                                             bounds=(0, 0, 1, 1), backend="synthetic"),
                            lambda: RawSource())
    grant = ScreenShareGrant("owner-A", "openai_responses:vision", "gpt-6-astra",
                             ("display:raw",), 5_000_000_000)
    session = manager.open_session({"sources": [{"source_id": "display:raw"}],
                                    "destination": "openai_responses:vision",
                                    "model": "gpt-6-astra",
                                    "delivery_mode": "sampled_image"},
                                   grant=grant, owner_ref="owner-A", now_ns=1_000_000_000)
    manager.start_session(session["session_id"], owner_ref="owner-A", now_ns=1_100_000_000)
    event = manager.producer_tick(session["session_id"], owner_ref="owner-A",
                                  now_ns=1_200_000_000)[0]
    assert event["media_type"] == "application/octet-stream"


def test_native_video_is_typed_unavailable_not_silently_downgraded_to_text():
    with pytest.raises(DeliveryError) as err:
        deliver_native_video()
    assert err.value.code == "NATIVE_VIDEO_UNAVAILABLE"

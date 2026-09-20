import math

import pytest

from harness.studio_body_contract import (
    BodyContractError,
    CONTRACT_VERSION,
    SOUND_ACTION_KIND,
    SOUND_TARGET_PREFIX,
    build_body_snapshot,
    parse_body_step,
)


def _step(**overrides):
    body = {
        "schema": CONTRACT_VERSION,
        "client_action_id": "client-1",
        "idempotency_key": "idem-1",
        "model_route_ref": "deterministic-stub/v1",
        "observation_ref": "obs_seed",
        "action": {
            "kind": SOUND_ACTION_KIND,
            "target": SOUND_TARGET_PREFIX + "session-1/instrument-1",
            "args": {"seed": 58, "duration_s": 6.0, "root_hz": 220.0},
        },
    }
    body.update(overrides)
    return body


def test_sound_body_step_rejects_malformed_controls_without_defaults():
    cases = [
        ("seed", "58"),
        ("seed", True),
        ("duration_s", "6"),
        ("duration_s", math.nan),
        ("duration_s", 3.0),
        ("root_hz", None),
        ("root_hz", 20.0),
    ]
    for key, value in cases:
        body = _step()
        body["action"]["args"][key] = value
        with pytest.raises(BodyContractError):
            parse_body_step(body)


def test_body_step_preserves_image_delivery_parts_as_refs():
    body = _step(
        capture_session_ref="cap-main",
        latest_frame_ref="frame-0007",
        latest_delivered_frame_age_ms=42,
        model_delivery={
            "parts": [{
                "kind": "image",
                "frame_ref": "frame-0007",
                "content_type": "image/png",
                "sha256": "a" * 64,
                "byte_length": 1203,
            }]
        },
    )

    step = parse_body_step(body)
    content = step.accountable_content()

    assert content["capture_session_ref"] == "cap-main"
    assert content["latest_frame_ref"] == "frame-0007"
    assert content["model_delivery"]["parts"][0]["kind"] == "image"
    assert content["model_delivery"]["parts"][0]["sha256"] == "a" * 64


def test_body_snapshot_does_not_promote_requested_frame_refs_to_evidence():
    snapshot = build_body_snapshot(
        "session-1",
        "instrument-1",
        capture_request={
            "capture_session_ref": "cap-main",
            "source_ref": "monitor-1",
            "latest_frame_ref": "frame-0007",
            "latest_delivered_frame_age_ms": 42,
        },
        now=lambda: "2026-09-15T12:00:00Z",
    )

    assert snapshot["schema"] == "flywheel.studio.body.snapshot/v1"
    assert snapshot["snapshot"]["session_ref"] == "session-1"
    assert snapshot["snapshot"]["capture_session_ref"] is None
    assert snapshot["snapshot"]["latest_frame_ref"] is None
    assert snapshot["snapshot"]["capture"]["status"] == "capture_manager_unavailable"
    assert snapshot["snapshot"]["requested_capture"]["latest_frame_ref"] == "frame-0007"
    assert snapshot["snapshot"]["requested_capture"]["validated"] is False
    assert snapshot["snapshot"]["observations"][0]["delivery_mode"] == "measured_text_json"

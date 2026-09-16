import json
import os
import sys
from pathlib import Path

import pytest

from harness import gateway
from harness.studio_body_contract import CONTRACT_VERSION
from harness.studio_body_engine import (
    ENGINE_ACTION_KIND,
    ENGINE_TARGET_PREFIX,
    StudioBodyEngineEffector,
    studio_engine_read_scope,
)
from harness.studio_body_route import handle_body_step_post
from tests.test_live_screen_provider_delivery import OWNER
from tests.test_studio_body_delivery_receipt_binding import _deliver


def _add_accountable_sources(monkeypatch, tmp_path):
    for name in ("COHERENCE_MEMBRANE_SRC", "PROOF_SURFACE_SRC", "ACCOUNTABLE_SURFACE_SRC"):
        path = _configured_path(name)
        assert path.exists(), path
        sys.path.insert(0, str(path))
    engine = _configured_path("STUDIO_ENGINE_SRC")
    monkeypatch.setenv("STUDIO_ENGINE_SRC", str(engine))
    monkeypatch.setenv("ACCOUNTABLE_SURFACE_GRANTS", str(tmp_path / "grants.json"))
    monkeypatch.setenv("ACCOUNTABLE_SURFACE_AUTHORITY_STATE", str(tmp_path / "authority.sqlite3"))


def _configured_path(name: str) -> Path:
    value = os.environ.get(name)
    if not value:
        pytest.skip(f"{name} not configured for accepted-source Studio body integration")
    path = Path(value)
    assert path.exists(), f"{name}={path} does not exist"
    return path


def _engine_grant(bound):
    return {
        "authorization_version": "0.1",
        "receipt_id": "rcpt-studio-engine-screen",
        "kind": "authorization-grant",
        "principal": {"id": "operator-1", "role": "operator"},
        "agent": {"id": "studio-body-screen-test"},
        "intent": "render one bounded Studio Engine visual world from screen delivery",
        "scope": {
            "allowed_actions": [ENGINE_ACTION_KIND],
            "allowed_targets": [],
            "allowed_reads": [studio_engine_read_scope(phases=("before", "after", "rollback"))],
            "allowed_bounds": [bound],
            "max_actions": 1,
        },
        "granted_at": "2026-09-15T00:00:00+00:00",
        "expires_at": "2030-01-01T00:00:00+00:00",
        "revoked": False,
    }


def test_delivered_frame_can_drive_studio_engine_action_with_feedback(tmp_path, monkeypatch):
    session_id, manager, scheduler, delivery = _deliver(tmp_path, monkeypatch)
    _add_accountable_sources(monkeypatch, tmp_path)
    effector = StudioBodyEngineEffector()
    (tmp_path / "grants.json").write_text(
        json.dumps([_engine_grant(effector.bound())]), encoding="utf-8")

    body, code = handle_body_step_post({
        "schema": CONTRACT_VERSION,
        "client_action_id": "client-screen-engine-1",
        "idempotency_key": "idem-screen-engine-1",
        "model_route_ref": "openai_responses:vision",
        "observation_ref": "obs-screen-frame-1",
        "capture_session_ref": session_id,
        "latest_frame_ref": "display:primary:1",
        "latest_delivered_frame_age_ms": 100,
        "model_delivery": {"parts": [{
            "kind": "screen_frame",
            "frame": delivery["frame"],
            "model_route": delivery["model_route"],
            "model": delivery["model"],
            "delivery_ref": delivery["delivery_ref"],
            "delivery_receipt_sha256": delivery["delivery_receipt_sha256"],
        }]},
        "action": {"kind": ENGINE_ACTION_KIND,
                   "target": ENGINE_TARGET_PREFIX + "studio-screen-1/screen",
                   "args": {"seed": 7, "generator": "gyroid",
                            "scheme": "analogous", "max_steps": 4,
                            "target": 0.9, "floor": 0.6,
                            "render_frames": True}},
    }, capture_manager=manager, capture_scheduler=scheduler,
        owner_ref=OWNER, now_ns=1_200_000_000)

    assert code == 200
    assert body["accepted"] is True
    assert body["receipt"]["frame_count"] > 0
    assert body["receipt"]["frames"][0]["png_base64"]
    assert body["authority_receipt"]["authority_state"]["usage_counted"] == 1

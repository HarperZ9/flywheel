import json
import os
import sys
from pathlib import Path

import pytest

from harness.studio_body_contract import CONTRACT_VERSION
from harness.studio_body_engine import (
    ENGINE_ACTION_KIND,
    ENGINE_TARGET_PREFIX,
    StudioBodyEngineEffector,
    make_studio_engine_exposed,
    parse_engine_body_step,
    render_studio_engine_world,
    studio_engine_read_scope,
)


def _body():
    return {
        "schema": CONTRACT_VERSION,
        "client_action_id": "client-engine-1",
        "idempotency_key": "idem-engine-1",
        "model_route_ref": "deterministic-stub/v1",
        "observation_ref": "obs_engine_seed",
        "action": {
            "kind": ENGINE_ACTION_KIND,
            "target": ENGINE_TARGET_PREFIX + "session-1/visual-1",
            "args": {
                "seed": 7,
                "generator": "gyroid",
                "scheme": "analogous",
                "max_steps": 4,
                "target": 0.9,
                "floor": 0.6,
                "render_frames": True,
            },
        },
        "model_delivery": {"parts": [{"kind": "text", "text": "render a gyroid world"}]},
    }


def _add_sources(monkeypatch, tmp_path):
    for name in ("COHERENCE_MEMBRANE_SRC", "PROOF_SURFACE_SRC", "ACCOUNTABLE_SURFACE_SRC"):
        p = _configured_path(name)
        sys.path.insert(0, str(p))
    engine_src = _configured_path("STUDIO_ENGINE_SRC")
    monkeypatch.setenv("STUDIO_ENGINE_SRC", str(engine_src))
    monkeypatch.setenv("ACCOUNTABLE_SURFACE_GRANTS", str(tmp_path / "grants.json"))
    monkeypatch.setenv("ACCOUNTABLE_SURFACE_AUTHORITY_STATE", str(tmp_path / "authority.sqlite3"))


def _configured_path(name: str) -> Path:
    value = os.environ.get(name)
    if not value:
        pytest.skip(f"{name} not configured for accepted-source Studio body integration")
    path = Path(value)
    assert path.exists(), f"{name}={path} does not exist"
    return path


def _grant(bound):
    return {
        "authorization_version": "0.1",
        "receipt_id": "rcpt-studio-engine",
        "kind": "authorization-grant",
        "principal": {"id": "operator-1", "role": "operator"},
        "agent": {"id": "studio-body-engine-test"},
        "intent": "render one bounded Studio Engine visual world",
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


def test_engine_step_runs_accepted_source_and_returns_rendered_frame(monkeypatch, tmp_path):
    _add_sources(monkeypatch, tmp_path)
    step = parse_engine_body_step(_body())

    receipt = render_studio_engine_world(step)

    assert receipt["schema"] == "flywheel.studio.body.engine-render-receipt/v1"
    assert receipt["engine_head"] == "81810e14c6902d3cb750c25c7c15d063ac723926"
    assert receipt["world"]["id"] == receipt["world_id"]
    assert receipt["render_program"]["target"] == "glsl-fragment"
    assert receipt["frame_count"] > 0
    assert receipt["frames"][0]["png_base64"]
    assert len(receipt["frames"][0]["frame_sha256"]) == 64
    assert receipt["frames"][0]["sha256"] in receipt["engine_receipt"]["artifact_shas"]


def test_engine_action_runs_through_accountable_surface_remote_durable(monkeypatch, tmp_path):
    _add_sources(monkeypatch, tmp_path)
    from accountable_surface.authority_store import AuthorityStore
    from accountable_surface.registry import EffectorRegistry
    from accountable_surface.remote_actuation import actuate_impl
    from accountable_surface.surface import AccountableSurface

    step = parse_engine_body_step(_body())
    effector = StudioBodyEngineEffector()
    Path(tmp_path / "grants.json").write_text(json.dumps([_grant(effector.bound())]), encoding="utf-8")
    store = AuthorityStore(str(tmp_path / "grants.json"),
                           authority_state_path=str(tmp_path / "authority.sqlite3"))
    registry = EffectorRegistry({ENGINE_ACTION_KIND: make_studio_engine_exposed(effector)}, [])

    out = actuate_impl(
        AccountableSurface(), store, registry, ENGINE_ACTION_KIND, step.target,
        step.accountable_content_json(), idempotency_key=step.idempotency_key)

    result = effector.last_result(step.target)
    assert out["decision"] == "allow"
    assert out["acted"] is True
    assert out["verified"] is True
    assert result["world_id"]
    assert result["frame_count"] > 0


def test_body_step_route_runs_engine_action_with_configured_authority(monkeypatch, tmp_path):
    _add_sources(monkeypatch, tmp_path)
    from harness.studio_body_route import handle_body_step_post

    effector = StudioBodyEngineEffector()
    Path(tmp_path / "grants.json").write_text(json.dumps([_grant(effector.bound())]), encoding="utf-8")

    body, code = handle_body_step_post(_body())

    assert code == 200
    assert body["accepted"] is True
    assert body["action_kind"] == ENGINE_ACTION_KIND
    assert body["receipt"]["world_id"]
    assert body["receipt"]["frame_count"] > 0
    assert body["authority_receipt"]["authority_state"]["usage_counted"] == 1

import json
import os
import sys

import pytest

from harness.studio_body_contract import (
    CONTRACT_VERSION,
    SOUND_ACTION_KIND,
    SOUND_TARGET_PREFIX,
    parse_body_step,
)
from harness.studio_body_sound import (
    StudioBodySoundEffector,
    make_studio_sound_exposed,
    studio_sound_read_scope,
)


def _add_source_path(env_name):
    value = os.environ.get(env_name)
    if not value:
        pytest.skip(f"{env_name} is not configured for source-level Accountable Surface test")
    sys.path.insert(0, value)


def _step():
    return parse_body_step(_step_body())


def _step_body():
    return {
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
        "model_delivery": {"parts": [{"kind": "text", "text": "compose bounded chime"}]},
    }


def _grant(bound):
    return {
        "authorization_version": "0.1",
        "receipt_id": "rcpt-studio-body",
        "kind": "authorization-grant",
        "principal": {"id": "operator-1", "role": "operator"},
        "agent": {"id": "studio-body-test"},
        "intent": "compose one bounded Flywheel Studio sound instrument",
        "scope": {
            "allowed_actions": [SOUND_ACTION_KIND],
            "allowed_targets": [],
            "allowed_reads": [studio_sound_read_scope(phases=("before", "after", "rollback"))],
            "allowed_bounds": [bound],
            "max_actions": 1,
        },
        "granted_at": "2026-09-15T00:00:00+00:00",
        "expires_at": "2030-01-01T00:00:00+00:00",
        "revoked": False,
    }


def test_sound_body_action_runs_through_accountable_surface_remote_durable(tmp_path):
    _add_source_path("COHERENCE_MEMBRANE_SRC")
    _add_source_path("PROOF_SURFACE_SRC")
    _add_source_path("ACCOUNTABLE_SURFACE_SRC")

    from accountable_surface.authority_store import AuthorityStore
    from accountable_surface.registry import EffectorRegistry
    from accountable_surface.remote_actuation import actuate_impl
    from accountable_surface.surface import AccountableSurface

    step = _step()
    effector = StudioBodySoundEffector()
    grants_path = tmp_path / "grants.json"
    state_path = tmp_path / "authority.sqlite3"
    grants_path.write_text(json.dumps([_grant(effector.bound())]), encoding="utf-8")
    store = AuthorityStore(str(grants_path), authority_state_path=str(state_path))
    registry = EffectorRegistry({SOUND_ACTION_KIND: make_studio_sound_exposed(effector)}, [])

    out = actuate_impl(
        AccountableSurface(),
        store,
        registry,
        SOUND_ACTION_KIND,
        step.target,
        step.accountable_content_json(),
        idempotency_key=step.idempotency_key,
    )

    result = effector.last_result(step.target)
    assert out["decision"] == "allow"
    assert out["acted"] is True
    assert out["verified"] is True
    assert out["authority_state"]["usage_counted"] == 1
    assert result["receipt"]["wav_sha256"]
    assert result["receipt"]["duration_s"] == 6.0


def test_gateway_body_step_runs_sound_action_with_configured_accountable_authority(
        tmp_path, monkeypatch):
    _add_source_path("COHERENCE_MEMBRANE_SRC")
    _add_source_path("PROOF_SURFACE_SRC")
    _add_source_path("ACCOUNTABLE_SURFACE_SRC")

    from harness.studio_body_route import handle_body_step_post

    effector = StudioBodySoundEffector()
    grants_path = tmp_path / "grants.json"
    state_path = tmp_path / "authority.sqlite3"
    grants_path.write_text(json.dumps([_grant(effector.bound())]), encoding="utf-8")
    monkeypatch.setenv("ACCOUNTABLE_SURFACE_GRANTS", str(grants_path))
    monkeypatch.setenv("ACCOUNTABLE_SURFACE_AUTHORITY_STATE", str(state_path))

    body, code = handle_body_step_post(_step_body())

    assert code == 200
    assert body["accepted"] is True
    assert body["status"] == "accepted"
    assert body["receipt"]["receipt"]["wav_sha256"]
    assert body["authority_receipt"]["authority_state"]["usage_counted"] == 1

from __future__ import annotations

import copy
import json

import pytest


from tests.frozen_studio_fixtures import (
    ENGINE_ACTION_KIND, ENGINE_TARGET, _PNG_SHA256, _StudioStub,
)

def test_studio_fixture_writes_bounded_engine_grant_and_env(tmp_path):
    from scripts.frozen_gateway_studio_smoke import prepare_studio_smoke_fixture

    fixture = prepare_studio_smoke_fixture(tmp_path / "home")

    assert set(fixture.env) == {
        "ACCOUNTABLE_SURFACE_GRANTS",
        "ACCOUNTABLE_SURFACE_AUTHORITY_STATE",
        "ACCOUNTABLE_SURFACE_JOURNAL",
    }
    assert fixture.env["ACCOUNTABLE_SURFACE_GRANTS"] == str(fixture.grants_path)
    assert fixture.env["ACCOUNTABLE_SURFACE_AUTHORITY_STATE"] == str(fixture.state_path)
    assert fixture.env["ACCOUNTABLE_SURFACE_JOURNAL"] == str(fixture.journal_path)
    assert fixture.state_path.parent == fixture.home
    assert fixture.journal_path.parent == fixture.home

    grants = json.loads(fixture.grants_path.read_text(encoding="utf-8"))
    assert len(grants) == 1
    grant = grants[0]
    assert grant["kind"] == "authorization-grant"
    assert grant["agent"]["id"] == "frozen-studio-smoke"
    assert grant["scope"]["allowed_actions"] == [ENGINE_ACTION_KIND]
    assert grant["scope"]["allowed_targets"] == [ENGINE_TARGET]
    assert grant["scope"]["allowed_bounds"] == [
        {"kind": "api", "origins": ["flywheel://studio"], "intents": ["render_world"]}
    ]
    assert grant["scope"]["max_actions"] == 1
    assert grant["scope"]["allowed_reads"] == [{
        "observation_kind": "api.resource",
        "phases": ["before", "after", "rollback"],
        "target_scope": {
            "kind": "api",
            "service": "flywheel-studio-body",
            "origins": ["flywheel://studio"],
            "intents": ["render_world"],
            "paths": ["/engine/session-1/visual-1"],
        },
    }]


def test_studio_fixture_refuses_to_overwrite_authority_files(tmp_path):
    from scripts.frozen_gateway_studio_smoke import prepare_studio_smoke_fixture

    home = tmp_path / "home"
    home.mkdir()
    (home / "studio-authority-grants.json").write_text("[]", encoding="utf-8")

    with pytest.raises(RuntimeError, match="STUDIO_FIXTURE_EXISTS"):
        prepare_studio_smoke_fixture(home)


def test_studio_smoke_denies_missing_bearer_and_accepts_bounded_render(tmp_path):
    from scripts.frozen_gateway_studio_smoke import (
        prepare_studio_smoke_fixture,
        run_studio_acceptance_smoke,
        validate_studio_smoke_summary,
    )

    fixture = prepare_studio_smoke_fixture(tmp_path / "home")
    stub = _StudioStub()

    summary = run_studio_acceptance_smoke(
        "http://127.0.0.1:1", "local-token", fixture, request=stub.request)

    validate_studio_smoke_summary(summary)
    assert summary["schema"] == "flywheel.frozen-gateway-studio-smoke/v1"
    assert summary["unauthenticated_status"] == 401
    assert summary["status"]["authority_configured"] is True
    assert summary["status"]["backend_ready"] is False
    assert summary["ungranted_action_status"] == 403
    assert summary["off_target_action_status"] == 403
    assert summary["exact_scope_checked"] is True
    assert summary["accepted"] is True
    assert summary["action_kind"] == ENGINE_ACTION_KIND
    assert summary["target"] == ENGINE_TARGET
    assert summary["world_id"] == "world-smoke"
    assert summary["frame_count"] == 1
    assert summary["first_frame_sha256"] == _PNG_SHA256
    assert summary["authority"] == {
        "decision": "allow",
        "acted": True,
        "verified": True,
        "usage_counted": 1,
    }
    assert summary["exhausted_action_status"] == 403
    assert summary["unverified"] == ["semantic_render_criteria"]
    assert summary["routes"] == [
        "/api/studio/body/status",
        "/api/studio/body/status",
        "/api/studio/body/step",
        "/api/studio/body/step",
        "/api/studio/body/step",
        "/api/studio/body/step",
    ]
    step_targets = [body["action"]["target"] for path, _token, body in stub.calls
                    if path == "/api/studio/body/step"]
    assert step_targets == [
        "flywheel://studio/sound/session-1/instrument-1",
        "flywheel://studio/engine/session-1/visual-2",
        ENGINE_TARGET,
        ENGINE_TARGET,
    ]
    assert len(stub.engine_bodies) == 2
    assert stub.engine_bodies[0]["idempotency_key"] != stub.engine_bodies[1]["idempotency_key"]
    summary_json = json.dumps(summary, sort_keys=True)
    assert "local-token" not in summary_json
    assert str(tmp_path) not in summary_json


def test_studio_summary_validation_rejects_extra_or_nested_secret_fields(tmp_path):
    from scripts.frozen_gateway_studio_smoke import (
        prepare_studio_smoke_fixture,
        run_studio_acceptance_smoke,
        validate_studio_smoke_summary,
    )

    summary = run_studio_acceptance_smoke(
        "http://127.0.0.1:1", "local-token",
        prepare_studio_smoke_fixture(tmp_path / "home"), request=_StudioStub().request)

    for mutated in (
        {**summary, "token": "local-token"},
        {**summary, "status": {**summary["status"], "raw_receipt": {}}},
        {**summary, "authority": {**summary["authority"], "journal_entry": {}}},
        {**summary, "exact_scope_checked": False},
    ):
        with pytest.raises(RuntimeError, match="STUDIO_SUMMARY"):
            validate_studio_smoke_summary(mutated)


def test_studio_smoke_rejects_corrupt_returned_png_hash(tmp_path):
    from scripts.frozen_gateway_studio_smoke import (
        prepare_studio_smoke_fixture,
        run_studio_acceptance_smoke,
    )

    fixture = prepare_studio_smoke_fixture(tmp_path / "home")
    stub = _StudioStub(corrupt_frame_hash=True)

    with pytest.raises(RuntimeError, match="STUDIO_FRAME_HASH"):
        run_studio_acceptance_smoke(
            "http://127.0.0.1:1", "local-token", fixture, request=stub.request)


@pytest.mark.parametrize("artifact_mode", [
    "missing_sha",
    "missing_artifact_shas",
    "artifact_shas_not_list",
    "nonhex_legacy",
    "artifact_not_member",
])
def test_studio_smoke_requires_legacy_artifact_id_membership(tmp_path, artifact_mode):
    from scripts.frozen_gateway_studio_smoke import (
        prepare_studio_smoke_fixture,
        run_studio_acceptance_smoke,
    )

    fixture = prepare_studio_smoke_fixture(tmp_path / "home")
    stub = _StudioStub(artifact_mode=artifact_mode)

    with pytest.raises(RuntimeError, match="STUDIO_FRAME_ARTIFACT_HASH"):
        run_studio_acceptance_smoke(
            "http://127.0.0.1:1", "local-token", fixture, request=stub.request)


def test_studio_smoke_requires_one_use_grant_exhaustion(tmp_path):
    from scripts.frozen_gateway_studio_smoke import (
        prepare_studio_smoke_fixture,
        run_studio_acceptance_smoke,
    )

    fixture = prepare_studio_smoke_fixture(tmp_path / "home")
    stub = _StudioStub(accept_exhausted=True)

    with pytest.raises(RuntimeError, match="STUDIO_ONE_USE_EXHAUSTION"):
        run_studio_acceptance_smoke(
            "http://127.0.0.1:1", "local-token", fixture, request=stub.request)


def test_studio_smoke_requires_ungranted_action_refusal(tmp_path):
    from scripts.frozen_gateway_studio_smoke import (
        prepare_studio_smoke_fixture,
        run_studio_acceptance_smoke,
    )

    fixture = prepare_studio_smoke_fixture(tmp_path / "home")
    stub = _StudioStub(accept_ungranted=True)

    with pytest.raises(RuntimeError, match="STUDIO_UNGRANTED_ACTION"):
        run_studio_acceptance_smoke(
            "http://127.0.0.1:1", "local-token", fixture, request=stub.request)


def test_studio_smoke_requires_off_target_engine_refusal(tmp_path):
    from scripts.frozen_gateway_studio_smoke import (
        prepare_studio_smoke_fixture,
        run_studio_acceptance_smoke,
    )

    fixture = prepare_studio_smoke_fixture(tmp_path / "home")
    stub = _StudioStub(accept_off_target=True)

    with pytest.raises(RuntimeError, match="STUDIO_OFF_TARGET_ACTION"):
        run_studio_acceptance_smoke(
            "http://127.0.0.1:1", "local-token", fixture, request=stub.request)

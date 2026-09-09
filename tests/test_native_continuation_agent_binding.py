"""Continuation agent handoff must stay bound to its started Journey."""
from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import harness.continuation_route as continuation_route

from harness.evidence_json import canonical_bytes, canonical_sha256
from harness.gateway_grant_route import gateway_grant_post
from harness.gateway_operation_route import route_gateway_operation
from harness.journey_store import JourneyStore, MutationCommand

from test_native_continuation_agent_handoff import (
    CaptureFactory,
    HANDOFF_SCHEMA,
    NOW,
    OWNER,
    _agent_service,
    _continuation_post,
    _export,
    _final_body,
    _git_root,
    _operation_body,
    _prepare_approve,
    _preview_start_context,
)

BINDING_SCHEMA = "flywheel.native-continuation-start-binding/v1"


def _ordinary_journey(state: Path, suffix: str = "b") -> dict:
    ack = JourneyStore(state).create(MutationCommand(
        OWNER, "jrn_" + suffix * 32, None, "ordinary-" + suffix,
        "intake", {"legacy_label": None, "goal": "ordinary work",
                   "intake": {}, "occurred_at": NOW}))
    return {"journey_ref": ack.journey_ref,
            "event_head_sha256": ack.event_head_sha256}


def _preview_context_without_start(tmp_path: Path):
    root, state = _git_root(tmp_path), tmp_path / "state"
    preview, preview_status = _continuation_post(
        "/api/continuation/preview",
        {"root": str(root), "export_path": str(_export(tmp_path))},
        state, root)
    assert preview_status == 200
    context, context_status = _continuation_post(
        "/api/continuation/context", {
            "preview_ref": preview["preview_ref"],
            "preview_sha256": preview["preview_sha256"],
            "source_state_sha256": preview["source_state_sha256"],
        }, state)
    assert context_status == 200
    return state, preview, context


def _binding_path(state: Path, preview_ref: str) -> Path:
    return state / "continuation" / "starts" / OWNER / f"{preview_ref}.json"


def _write_binding(state: Path, preview: dict, journey: dict,
                   *, journey_ref: str | None = None) -> None:
    value = {
        "schema": BINDING_SCHEMA,
        "owner_ref": OWNER,
        "preview_ref": preview["preview_ref"],
        "preview_sha256": preview["preview_sha256"],
        "source_state_sha256": preview["source_state_sha256"],
        "journey_ref": journey_ref or journey["journey_ref"],
        "start_client_request_id": "continuation-start",
        "recovery_client_request_id": "continuation-start:recovery-action",
        "recovery_event_sha256": journey["event_sha256"],
        "recovery_event_head_sha256": journey["event_head_sha256"],
        "recovery_action_id": "continue-" + preview["preview_ref"],
    }
    value["binding_sha256"] = canonical_sha256(value)
    path = _binding_path(state, preview["preview_ref"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value))


def test_duplicate_start_serializes_one_journey_without_orphan(tmp_path,
                                                              monkeypatch):
    root, state = _git_root(tmp_path), tmp_path / "state"
    preview, preview_status = _continuation_post(
        "/api/continuation/preview",
        {"root": str(root), "export_path": str(_export(tmp_path))},
        state, root)
    assert preview_status == 200
    original = continuation_route._grant_and_run
    entered_create = 0
    entered_lock = threading.Lock()

    def delayed_grant_and_run(action, request, **kwargs):
        nonlocal entered_create
        if action == "create":
            with entered_lock:
                entered_create += 1
            time.sleep(0.05)
        return original(action, request, **kwargs)

    monkeypatch.setattr(
        continuation_route, "_grant_and_run", delayed_grant_and_run)
    start = {"preview_ref": preview["preview_ref"],
             "preview_sha256": preview["preview_sha256"],
             "source_state_sha256": preview["source_state_sha256"],
             "client_request_id": "continuation-start"}

    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(lambda _: _continuation_post(
            "/api/continuation/start", start, state), range(12)))

    assert [(status, body.get("error", {}).get("code"))
            for body, status in results] == [(200, None)] * 12
    refs = {body["journey"]["journey_ref"] for body, _ in results}
    assert len(refs) == 1
    assert sum(1 for body, _ in results
               if not body["journey"].get("idempotent_replay")) == 1
    owner_dir = state / "journeys" / "v2" / "owners" / OWNER
    assert sorted(path.name for path in owner_dir.glob("jrn_*")) == list(refs)
    assert entered_create == 1


def test_duplicate_start_different_request_ids_replay_one_preview_journey(
        tmp_path, monkeypatch):
    root, state = _git_root(tmp_path), tmp_path / "state"
    preview, preview_status = _continuation_post(
        "/api/continuation/preview",
        {"root": str(root), "export_path": str(_export(tmp_path))},
        state, root)
    assert preview_status == 200
    original = continuation_route._grant_and_run
    entered_create = 0
    entered_lock = threading.Lock()

    def delayed_grant_and_run(action, request, **kwargs):
        nonlocal entered_create
        if action == "create":
            with entered_lock:
                entered_create += 1
            time.sleep(0.05)
        return original(action, request, **kwargs)

    monkeypatch.setattr(
        continuation_route, "_grant_and_run", delayed_grant_and_run)

    def start_one(index: int):
        start = {"preview_ref": preview["preview_ref"],
                 "preview_sha256": preview["preview_sha256"],
                 "source_state_sha256": preview["source_state_sha256"],
                 "client_request_id": f"continuation-start-{index}"}
        return _continuation_post("/api/continuation/start", start, state)

    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(start_one, range(12)))

    assert [(status, body.get("error", {}).get("code"))
            for body, status in results] == [(200, None)] * 12
    refs = {body["journey"]["journey_ref"] for body, _ in results}
    assert len(refs) == 1
    owner_dir = state / "journeys" / "v2" / "owners" / OWNER
    assert sorted(path.name for path in owner_dir.glob("jrn_*")) == list(refs)
    assert entered_create == 1


def test_continuation_agent_grant_refuses_cross_journey_handoff(tmp_path):
    _, state, preview, started, context = _preview_start_context(tmp_path)
    other = _ordinary_journey(state)
    body = _operation_body(preview, {"journey": other}, context)

    prepared, status = gateway_grant_post(
        "/api/gateway-grants/prepare/agent.run", json.dumps(body).encode(),
        owner_ref=OWNER, state_root=state, clock=lambda: NOW)

    assert status == 409
    assert prepared["error"]["code"] == "CONTINUATION_JOURNEY_MISMATCH"


def test_continuation_agent_grant_refuses_preview_without_start(tmp_path):
    state, preview, context = _preview_context_without_start(tmp_path)
    other = _ordinary_journey(state)
    body = _operation_body(preview, {"journey": other}, context)

    prepared, status = gateway_grant_post(
        "/api/gateway-grants/prepare/agent.run", json.dumps(body).encode(),
        owner_ref=OWNER, state_root=state, clock=lambda: NOW)

    assert status == 409
    assert prepared["error"]["code"] == "CONTINUATION_NOT_STARTED"


def test_continuation_agent_dispatch_refuses_late_binding_drift(tmp_path):
    _, state, preview, started, context = _preview_start_context(tmp_path)
    body = _operation_body(preview, started, context)
    approved = _prepare_approve(state, body)
    other = _ordinary_journey(state)
    _write_binding(state, preview, started["journey"],
                   journey_ref=other["journey_ref"])
    factory = CaptureFactory()

    response = route_gateway_operation(
        "POST", "/api/agent", owner_ref=OWNER,
        raw=_final_body(body, approved["grant_ref"]),
        content_type="application/json", service=_agent_service(state),
        process_factory=factory)

    assert response.status == 409
    assert response.body["error"]["code"] == "CONTINUATION_BINDING_DRIFT"
    assert factory.calls == 0

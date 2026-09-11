"""Continuation-to-agent handoff regressions.

These tests prove the Rescue continuation can reach the existing /api/agent
operation path only through an exact grant carrying source-bound private context.
"""
from __future__ import annotations

import json
import subprocess
from copy import deepcopy
from pathlib import Path

from harness.continuation_route import handle_continuation_post
from harness.gateway_grant_route import gateway_grant_post
from harness.gateway_operation import thaw_operation
from harness.gateway_operation_process import WorkerOutcome
from harness.gateway_operation_route import route_gateway_operation
from harness.gateway_operations import GatewayOperations
from harness.journey_service import JourneyService
from harness.journey_store import JourneyStore
from harness.operation_grants import GrantStore

NOW = "2026-09-08T12:00:00Z"
OWNER = "owner_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
HANDOFF_SCHEMA = "flywheel.native-continuation-agent-handoff/v1"


class Process:
    control_class = "windows_job_v1"

    def __init__(self, outcome: WorkerOutcome) -> None:
        self.outcome = outcome

    def resume(self) -> bool:
        return True

    def signal_tree(self) -> bool:
        return True

    def wait(self, _timeout):
        return self.outcome

    def close(self) -> None:
        pass


class CaptureFactory:
    def __init__(self) -> None:
        self.authorized = []
        self.calls = 0

    def create(self, authorized, progress):
        self.calls += 1
        self.authorized.append(authorized)
        progress({"type": "assistant", "text": "continuation routed"})
        return Process(WorkerOutcome("completed", {"final": "routed"}))


def _git_commit(root: Path, message: str) -> None:
    subprocess.run([
        "git", "-C", str(root),
        "-c", "user.email=a@example.invalid",
        "-c", "user.name=A",
        "commit", "-q", "-m", message],
        check=True)


def _git_root(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "AGENTS.md").write_text("Run focused tests.\n", encoding="utf-8")
    (root / "slugger.py").write_text(
        "def normalize_title(value):\n    return value\n",
        encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    _git_commit(root, "init")
    return root


def _export(tmp_path: Path) -> Path:
    path = tmp_path / "continuation-export.jsonl"
    path.write_text(
        "user: Continue parser repair. Implement normalize_title exactly.\n"
        "user: Keep slugger.py in scope. Run the existing tests.\n"
        "unfinished: Finish title normalization without editing tests.\n"
        "artifact: slugger.py\n",
        encoding="utf-8")
    return path


def _continuation_post(path: str, body: dict, state: Path, root: Path | None = None):
    return handle_continuation_post(
        path, json.dumps(body).encode(), owner_ref=OWNER,
        state_root=state, root=root, clock=lambda: NOW)


def _preview_start_context(tmp_path: Path):
    root, state = _git_root(tmp_path), tmp_path / "state"
    preview, preview_status = _continuation_post(
        "/api/continuation/preview",
        {"root": str(root), "export_path": str(_export(tmp_path))},
        state, root)
    assert preview_status == 200
    started, start_status = _continuation_post(
        "/api/continuation/start", {
            "preview_ref": preview["preview_ref"],
            "preview_sha256": preview["preview_sha256"],
            "source_state_sha256": preview["source_state_sha256"],
            "client_request_id": "continuation-start",
        }, state)
    assert start_status == 200
    context, context_status = _continuation_post(
        "/api/continuation/context", {
            "preview_ref": preview["preview_ref"],
            "preview_sha256": preview["preview_sha256"],
            "source_state_sha256": preview["source_state_sha256"],
        }, state)
    assert context_status == 200
    return root, state, preview, started, context


def _operation_body(preview: dict, started: dict, context: dict, **overrides):
    runner = context["runner_context"]
    selected_files = list(runner["selected_files"])
    operation = {
        "goal": runner["goal"],
        "endpoint": "stub",
        "max_steps": 2,
        "allow_write": False,
        "allow_exec": False,
        "stream": False,
        "root": runner["root"],
        "continuation": {
            "schema": HANDOFF_SCHEMA,
            "preview_ref": preview["preview_ref"],
            "preview_sha256": preview["preview_sha256"],
            "source_state_sha256": preview["source_state_sha256"],
            "selected_files": selected_files,
        },
        "data_refs": [],
        "credential_refs": [],
    }
    operation.update(overrides.pop("operation", {}))
    body = {
        "schema": "flywheel.gateway-operation/v1",
        "journey_ref": started["journey"]["journey_ref"],
        "expected_event_head": started["journey"]["event_head_sha256"],
        "client_request_id": overrides.pop(
            "client_request_id", "continuation-agent-1"),
        "operation": operation,
    }
    body.update(overrides)
    return body


def _prepare_approve(state: Path, body: dict):
    prepared, status = gateway_grant_post(
        "/api/gateway-grants/prepare/agent.run",
        json.dumps(body).encode(), owner_ref=OWNER, state_root=state,
        clock=lambda: NOW)
    assert status == 200
    approved, approved_status = gateway_grant_post(
        "/api/gateway-grants/approve-once",
        json.dumps({"proposal_ref": prepared["proposal_ref"]}).encode(),
        owner_ref=OWNER, state_root=state, clock=lambda: NOW)
    assert approved_status == 200
    return approved


def _final_body(body: dict, grant_ref: str) -> bytes:
    return json.dumps({
        "schema": body["schema"],
        "journey_ref": body["journey_ref"],
        "expected_event_head": body["expected_event_head"],
        "client_request_id": body["client_request_id"],
        "grant_ref": grant_ref,
        **body["operation"],
    }).encode()


def _agent_service(state: Path) -> GatewayOperations:
    return GatewayOperations(state, clock=lambda: NOW, lock_timeout_s=30)


def _events(state: Path, journey_ref: str) -> list[dict]:
    service = JourneyService(owner_ref=OWNER, store=JourneyStore(state),
                             grants=GrantStore(state, clock=lambda: NOW),
                             clock=lambda: NOW)
    return service._events(journey_ref)


def test_continuation_rescue_action_launches_context_bound_agent_run(tmp_path):
    root, state, preview, started, context = _preview_start_context(tmp_path)
    journey_ref = started["journey"]["journey_ref"]
    body = _operation_body(preview, started, context)
    approved = _prepare_approve(state, body)
    factory = CaptureFactory()

    response = route_gateway_operation(
        "POST", "/api/agent", owner_ref=OWNER,
        raw=_final_body(body, approved["grant_ref"]),
        content_type="application/json", service=_agent_service(state),
        process_factory=factory)

    assert response.status == 200
    assert response.body == {"final": "routed"}
    assert factory.calls == 1
    operation = thaw_operation(factory.authorized[0].operation)
    assert operation["root"] == str(root.resolve())
    assert "Implement normalize_title exactly" in operation["goal"]
    assert "Finish title normalization without editing tests" in operation["goal"]
    assert operation["continuation"] == {
        "schema": HANDOFF_SCHEMA,
        "preview_ref": preview["preview_ref"],
        "preview_sha256": preview["preview_sha256"],
        "source_state_sha256": preview["source_state_sha256"],
        "selected_files": ["slugger.py"],
    }
    events = _events(state, journey_ref)
    assert any(e["event_type"] == "record_next_action"
               and e["payload"]["next_actions"][0]["action_id"]
               == "continue-" + preview["preview_ref"] for e in events)
    operation_events = [e for e in events if e["event_type"].startswith("operation_")]
    assert [e["event_type"] for e in operation_events] == [
        "operation_queued", "operation_started", "operation_completed"]


def test_continuation_agent_grant_refuses_stale_source_before_proposal(tmp_path):
    root, state, preview, started, context = _preview_start_context(tmp_path)
    (root / "slugger.py").write_text("changed after preview\n", encoding="utf-8")

    prepared, status = gateway_grant_post(
        "/api/gateway-grants/prepare/agent.run",
        json.dumps(_operation_body(preview, started, context)).encode(),
        owner_ref=OWNER, state_root=state, clock=lambda: NOW)

    assert status == 409
    assert prepared["error"]["code"] == "SOURCE_DRIFT"


def test_continuation_agent_dispatch_refuses_source_drift_after_approval(
        tmp_path):
    root, state, preview, started, context = _preview_start_context(tmp_path)
    body = _operation_body(preview, started, context)
    approved = _prepare_approve(state, body)
    (root / "slugger.py").write_text("changed after approval\n", encoding="utf-8")
    factory = CaptureFactory()

    response = route_gateway_operation(
        "POST", "/api/agent", owner_ref=OWNER,
        raw=_final_body(body, approved["grant_ref"]),
        content_type="application/json", service=_agent_service(state),
        process_factory=factory)

    assert response.status == 409
    assert response.body["error"]["code"] == "SOURCE_DRIFT"
    assert factory.calls == 0
    events = _events(state, started["journey"]["journey_ref"])
    assert "operation_queued" not in [e["event_type"] for e in events]


def test_continuation_agent_grant_refuses_mismatched_runner_root(tmp_path):
    _, state, preview, started, context = _preview_start_context(tmp_path)
    other = tmp_path / "other-root"
    other.mkdir()

    prepared, status = gateway_grant_post(
        "/api/gateway-grants/prepare/agent.run",
        json.dumps(_operation_body(
            preview, started, context, operation={"root": str(other)})).encode(),
        owner_ref=OWNER, state_root=state, clock=lambda: NOW)

    assert status == 422
    assert prepared["error"]["code"] == "CONTINUATION_ROOT_MISMATCH"


def test_continuation_agent_grant_is_exact_for_handoff_context(tmp_path):
    _, state, preview, started, context = _preview_start_context(tmp_path)
    body = _operation_body(preview, started, context)
    approved = _prepare_approve(state, body)
    changed = deepcopy(body)
    changed["operation"]["continuation"]["selected_files"] = []
    factory = CaptureFactory()

    response = route_gateway_operation(
        "POST", "/api/agent", owner_ref=OWNER,
        raw=_final_body(changed, approved["grant_ref"]),
        content_type="application/json", service=_agent_service(state),
        process_factory=factory)

    assert response.status == 403
    assert response.body["error"]["code"] == "PERMISSION_DENIED"
    assert factory.calls == 0

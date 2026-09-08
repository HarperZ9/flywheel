"""Provider-neutral continuation preview and Journey start route tests."""
from __future__ import annotations

import json
import io
import subprocess
from pathlib import Path

from harness.evidence_json import strict_load_json
from harness import gateway
from harness.journey_route import journey_post
from harness.continuation_route import handle_continuation_post

NOW = "2026-09-07T12:00:00Z"
OWNER = "owner_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


class _AdvancingClock:
    def __init__(self) -> None:
        self.count = 0

    def __call__(self) -> str:
        value = f"2026-09-07T12:00:{self.count:02d}Z"
        self.count += 1
        return value


def _post(path: str, body: dict | bytes, state: Path, root: Path | None = None,
          clock=lambda: NOW):
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    return handle_continuation_post(
        path, raw, owner_ref=OWNER, state_root=state, root=root,
        clock=clock)


def _journey(action: str, body: dict, state: Path):
    return journey_post(
        f"/api/journeys/{action}", json.dumps(body).encode(),
        owner_ref=OWNER, state_root=state,
        evidence_root=state / "artifacts", clock=lambda: NOW)


def _git_root(tmp_path: Path, *, dirty: bool = False) -> Path:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "AGENTS.md").write_text("Run the focused tests.\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "AGENTS.md"], cwd=root, check=True)
    subprocess.run([
        "git", "-c", "user.email=a@example.invalid", "-c", "user.name=A",
        "commit", "-q", "-m", "init"], cwd=root, check=True)
    if dirty:
        (root / "dirty.txt").write_text("local edit\n", encoding="utf-8")
    return root


def _export(tmp_path: Path, *, missing_attachment: bool = True) -> Path:
    path = tmp_path / "local-export.jsonl"
    attachment = (
        "attachment: missing-recording.mp3\n" if missing_attachment else "")
    path.write_text(
        "user: Continue the Flywheel maturity work from the repo state.\n"
        "summary: Previous compaction said Bulletin and Flywheel remain active.\n"
        "artifact: reports/current-status.md\n"
        "commit: c649cc8966b38ffbb8496499ce2bcebb21e76576\n"
        "unfinished: implement provider-neutral continuation preview.\n"
        f"{attachment}",
        encoding="utf-8")
    return path


def test_preview_names_repo_import_omissions_and_sanitizes_intake(tmp_path):
    root, state = _git_root(tmp_path, dirty=True), tmp_path / "state"
    result, status = _post("/api/continuation/preview", {
        "root": str(root), "export_path": str(_export(tmp_path))}, state, root)
    assert status == 200, result
    assert result["schema"] == "flywheel.native-continuation-preview/v1"
    assert result["source"]["root"] == str(root.resolve())
    assert result["repo"]["dirty_files"] == [
        {"path": "dirty.txt", "status": "??", "sha256": result["repo"]["dirty_files"][0]["sha256"]}]
    assert result["provider_native_resume"]["state"] == "unavailable"
    assert result["health"]["state"] == "blocked"
    assert any(row["source"] == "AGENTS.md" for row in result["import"]["mappings"])
    assert any(row["code"] == "MISSING_ATTACHMENT" for row in result["omissions"])
    intake = (state / "artifacts" / result["intake_ref"]).read_text(encoding="utf-8")
    assert str(tmp_path) not in intake and "missing-recording.mp3" in intake


def test_start_creates_one_source_bound_sanitized_journey_and_replays(tmp_path):
    root, state = _git_root(tmp_path, dirty=True), tmp_path / "state"
    preview, status = _post("/api/continuation/preview", {
        "root": str(root), "export_path": str(_export(
            tmp_path, missing_attachment=False))}, state, root)
    assert status == 200
    request = {
        "preview_ref": preview["preview_ref"],
        "preview_sha256": preview["preview_sha256"],
        "source_state_sha256": preview["source_state_sha256"],
        "client_request_id": "start-1",
    }
    first, first_status = _post("/api/continuation/start", request, state)
    second, second_status = _post("/api/continuation/start", request, state)
    assert first_status == second_status == 200
    assert first["journey"]["idempotent_replay"] is False
    assert second["journey"]["idempotent_replay"] is True
    listed, _ = _journey("list", {}, state)
    assert len(listed["journeys"]) == 1
    event_file = next((state / "journeys" / "v2" / "owners" / OWNER)
                      .glob("jrn_*/events/*.json"))
    event = strict_load_json(event_file.read_bytes())
    serialized = json.dumps(event, sort_keys=True)
    assert str(tmp_path) not in serialized
    assert event["payload"]["intake"]["preview_ref"] == preview["preview_ref"]
    assert event["payload"]["intake"]["provider_native_resume"]["state"] == "unavailable"
    package = event["payload"]["intake"]["context_package"]
    assert package["selected_task_count"] == 2
    assert package["selected_files"] == ["reports/current-status.md"]
    view, _ = _journey("resume", {
        "journey_ref": first["journey"]["journey_ref"], "lens": "Rescue"},
        state)
    assert view["next_actions"] == [{
        "action_id": "continue-" + preview["preview_ref"],
        "kind": "repair",
        "description": "Open the private continuation context and run the existing agent loop from the source-bound preview.",
        "basis_refs": [preview["preview_ref"], preview["intake_ref"]],
    }]


def test_start_retry_replays_with_advancing_clock_before_new_grant(tmp_path):
    clock = _AdvancingClock()
    root, state = _git_root(tmp_path), tmp_path / "state"
    preview, status = _post("/api/continuation/preview", {
        "root": str(root), "export_path": str(_export(
            tmp_path, missing_attachment=False))}, state, root, clock=clock)
    assert status == 200
    request = {
        "preview_ref": preview["preview_ref"],
        "preview_sha256": preview["preview_sha256"],
        "source_state_sha256": preview["source_state_sha256"],
        "client_request_id": "start-clock-retry",
    }
    first, first_status = _post(
        "/api/continuation/start", request, state, clock=clock)
    second, second_status = _post(
        "/api/continuation/start", request, state, clock=clock)
    assert first_status == second_status == 200
    assert first["journey"]["idempotent_replay"] is False
    assert second["journey"]["idempotent_replay"] is True
    listed, _ = _journey("list", {}, state)
    assert len(listed["journeys"]) == 1
    proposal_dir = state / "grant-proposals" / OWNER
    assert len(list(proposal_dir.glob("*.json"))) == 2


def test_start_refuses_stale_source_before_journey_creation(tmp_path):
    root, state = _git_root(tmp_path), tmp_path / "state"
    preview, status = _post("/api/continuation/preview", {
        "root": str(root), "export_path": str(_export(
            tmp_path, missing_attachment=False))}, state, root)
    assert status == 200
    (root / "later.txt").write_text("new local work\n", encoding="utf-8")
    result, start_status = _post("/api/continuation/start", {
        "preview_ref": preview["preview_ref"],
        "preview_sha256": preview["preview_sha256"],
        "source_state_sha256": preview["source_state_sha256"],
        "client_request_id": "start-stale",
    }, state)
    assert start_status == 409 and result["error"]["code"] == "SOURCE_DRIFT"
    listed, _ = _journey("list", {}, state)
    assert listed["journeys"] == []


def test_start_refuses_missing_required_state_before_journey_creation(tmp_path):
    root, state = _git_root(tmp_path), tmp_path / "state"
    preview, status = _post("/api/continuation/preview", {
        "root": str(root), "export_path": str(_export(tmp_path))}, state, root)
    assert status == 200 and preview["health"]["state"] == "blocked"
    result, start_status = _post("/api/continuation/start", {
        "preview_ref": preview["preview_ref"],
        "preview_sha256": preview["preview_sha256"],
        "source_state_sha256": preview["source_state_sha256"],
        "client_request_id": "start-missing-state",
    }, state)
    assert start_status == 409 and result["error"]["code"] == "CONTINUATION_BLOCKED"
    listed, _ = _journey("list", {}, state)
    assert listed["journeys"] == []


def test_continuation_requests_are_exact_and_null_body_is_400(tmp_path):
    state = tmp_path / "state"
    null_result, null_status = _post("/api/continuation/preview", b"null", state)
    extra_result, extra_status = _post("/api/continuation/start", {
        "preview_ref": "cpv_" + "a" * 32,
        "preview_sha256": "a" * 64,
        "source_state_sha256": "b" * 64,
        "client_request_id": "start-extra",
        "occurred_at": "2026-09-07T12:00:00Z",
    }, state)
    assert null_status == 400 and null_result["error"]["code"] == "INVALID_REQUEST"
    assert extra_status == 400 and extra_result["error"]["code"] == "UNKNOWN_FIELD"


def test_gateway_dispatches_preview_with_resolved_workspace_root(tmp_path, monkeypatch):
    root = _git_root(tmp_path)
    raw = json.dumps({"root": str(root)}).encode()
    handler = gateway._Handler.__new__(gateway._Handler)
    captured = []
    handler.path, handler.root = "/api/continuation/preview", tmp_path
    handler.flywheel_home = tmp_path / "home"
    handler.owner_ref = OWNER
    handler.clock = lambda: NOW
    handler.rfile = io.BytesIO(raw)
    handler._content_length = lambda: len(raw)
    handler._json = lambda body, code=200: captured.append((body, code))

    def called(path, body, **kwargs):
        assert path == "/api/continuation/preview" and body == raw
        assert kwargs["root"] == root.resolve()
        assert kwargs["state_root"] == handler.flywheel_home / "state"
        assert kwargs["owner_ref"] == OWNER
        return {"schema": "ok"}, 200

    monkeypatch.setattr(
        "harness.continuation_route.handle_continuation_post", called)
    handler._post()
    assert captured == [({"schema": "ok"}, 200)]


def test_undo_records_bounded_rollback_next_action_and_replays(tmp_path):
    root, state = _git_root(tmp_path), tmp_path / "state"
    preview, _ = _post("/api/continuation/preview", {
        "root": str(root), "export_path": str(_export(
            tmp_path, missing_attachment=False))}, state, root)
    started, status = _post("/api/continuation/start", {
        "preview_ref": preview["preview_ref"],
        "preview_sha256": preview["preview_sha256"],
        "source_state_sha256": preview["source_state_sha256"],
        "client_request_id": "start-undo",
    }, state)
    assert status == 200
    ack = started["journey"]
    request = {"journey_ref": ack["journey_ref"],
        "expected_event_head": ack["event_head_sha256"],
        "preview_ref": preview["preview_ref"],
        "preview_sha256": preview["preview_sha256"],
        "client_request_id": "undo-1"}
    first, first_status = _post("/api/continuation/undo", request, state)
    second, second_status = _post("/api/continuation/undo", request, state)
    assert first_status == second_status == 200
    assert second["journey"]["idempotent_replay"] is True
    view, _ = _journey("resume", {
        "journey_ref": ack["journey_ref"], "lens": "Rescue"}, state)
    assert view["next_actions"] == [{
        "action_id": "continue-" + preview["preview_ref"],
        "kind": "repair",
        "description": "Open the private continuation context and run the existing agent loop from the source-bound preview.",
        "basis_refs": [preview["preview_ref"], preview["intake_ref"]],
    }, {
        "action_id": "undo-" + preview["preview_ref"],
        "kind": "rollback",
        "description": "Review and detach this provider-neutral continuation package before another turn.",
        "basis_refs": [preview["preview_ref"]],
    }]


def test_undo_retry_replays_with_advancing_clock_without_second_action(tmp_path):
    clock = _AdvancingClock()
    root, state = _git_root(tmp_path), tmp_path / "state"
    preview, _ = _post("/api/continuation/preview", {
        "root": str(root), "export_path": str(_export(
            tmp_path, missing_attachment=False))}, state, root, clock=clock)
    started, status = _post("/api/continuation/start", {
        "preview_ref": preview["preview_ref"],
        "preview_sha256": preview["preview_sha256"],
        "source_state_sha256": preview["source_state_sha256"],
        "client_request_id": "start-before-undo-clock",
    }, state, clock=clock)
    assert status == 200
    ack = started["journey"]
    request = {"journey_ref": ack["journey_ref"],
        "expected_event_head": ack["event_head_sha256"],
        "preview_ref": preview["preview_ref"],
        "preview_sha256": preview["preview_sha256"],
        "client_request_id": "undo-clock-retry"}
    first, first_status = _post(
        "/api/continuation/undo", request, state, clock=clock)
    second, second_status = _post(
        "/api/continuation/undo", request, state, clock=clock)
    assert first_status == second_status == 200
    assert first["journey"]["idempotent_replay"] is False
    assert second["journey"]["idempotent_replay"] is True
    view, _ = _journey("resume", {
        "journey_ref": ack["journey_ref"], "lens": "Rescue"}, state)
    assert [row["kind"] for row in view["next_actions"]] == [
        "repair", "rollback"]
    proposal_dir = state / "grant-proposals" / OWNER
    assert len(list(proposal_dir.glob("*.json"))) == 3

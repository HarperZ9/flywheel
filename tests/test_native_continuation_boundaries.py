"""Continuation boundary regressions for source identity and privacy."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from harness.continuation_preview import MAX_EXPORT_BYTES, export_state
from harness.continuation_route import handle_continuation_post
from harness.evidence_json import strict_load_json
from harness.journey_route import journey_post

NOW = "2026-09-07T12:00:00Z"
OWNER = "owner_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def _post(path: str, body: dict | bytes, state: Path,
          root: Path | None = None):
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    return handle_continuation_post(
        path, raw, owner_ref=OWNER, state_root=state, root=root,
        clock=lambda: NOW)


def _journey(action: str, body: dict, state: Path):
    return journey_post(
        f"/api/journeys/{action}", json.dumps(body).encode(),
        owner_ref=OWNER, state_root=state,
        evidence_root=state / "artifacts", clock=lambda: NOW)


def _git_root(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "AGENTS.md").write_text("Run focused tests.\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "AGENTS.md"], cwd=root, check=True)
    subprocess.run([
        "git", "-c", "user.email=a@example.invalid", "-c", "user.name=A",
        "commit", "-q", "-m", "init"], cwd=root, check=True)
    return root


def _tracked_dirty_root(tmp_path: Path) -> Path:
    root = _git_root(tmp_path)
    tracked = root / "dirty.txt"
    tracked.write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "dirty.txt"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-m", "tracked"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   check=True)
    tracked.write_text("first dirty bytes\n", encoding="utf-8")
    return root


def _export(tmp_path: Path) -> Path:
    path = tmp_path / "local-export.jsonl"
    path.write_text(
        "user: Continue the Flywheel maturity work from the repo state.\n"
        "summary: Previous compaction said Bulletin and Flywheel remain active.\n"
        "artifact: reports/current-status.md\n"
        "unfinished: implement provider-neutral continuation preview.\n",
        encoding="utf-8")
    return path


def test_preview_hashes_dirty_git_status_shapes(tmp_path):
    root = _git_root(tmp_path)
    for name in ("tracked.txt", "staged.txt", "deleted.txt",
                 "rename-old.txt", "space file.txt"):
        (root / name).write_text(f"{name} base\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-m", "status shapes"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   check=True)
    (root / "tracked.txt").write_text("tracked worktree dirty\n", encoding="utf-8")
    (root / "staged.txt").write_text("staged dirty\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "staged.txt"], check=True)
    (root / "deleted.txt").unlink()
    subprocess.run(["git", "-C", str(root), "mv", "rename-old.txt",
                    "rename-new.txt"], check=True)
    (root / "space file.txt").write_text("space dirty\n", encoding="utf-8")
    (root / "untracked.txt").write_text("new file\n", encoding="utf-8")

    preview, status = _post("/api/continuation/preview", {"root": str(root)},
                            tmp_path / "state", root)

    assert status == 200
    by_path = {row["path"]: row for row in preview["repo"]["dirty_files"]}
    assert by_path["tracked.txt"]["status"] == " M"
    assert by_path["tracked.txt"]["sha256"]
    assert by_path["staged.txt"]["status"] == "M "
    assert by_path["staged.txt"]["sha256"]
    assert by_path["space file.txt"]["sha256"]
    assert by_path["rename-new.txt"]["sha256"]
    assert by_path["untracked.txt"]["sha256"]
    assert "sha256" not in by_path["deleted.txt"]


def test_start_refuses_tracked_dirty_byte_drift_before_journey_creation(tmp_path):
    root, state = _tracked_dirty_root(tmp_path), tmp_path / "state"
    preview, status = _post("/api/continuation/preview", {"root": str(root)},
                            state, root)
    assert status == 200
    assert preview["repo"]["dirty_files"] == [{
        "path": "dirty.txt", "status": " M",
        "sha256": preview["repo"]["dirty_files"][0]["sha256"]}]

    (root / "dirty.txt").write_text("changed after preview\n", encoding="utf-8")
    result, start_status = _post("/api/continuation/start", {
        "preview_ref": preview["preview_ref"],
        "preview_sha256": preview["preview_sha256"],
        "source_state_sha256": preview["source_state_sha256"],
        "client_request_id": "start-tracked-drift",
    }, state)

    assert start_status == 409 and result["error"]["code"] == "SOURCE_DRIFT"
    listed, _ = _journey("list", {}, state)
    assert listed["journeys"] == []


def test_public_intake_projects_private_context_and_excludes_credentials(tmp_path):
    root, state = _git_root(tmp_path), tmp_path / "state"
    export = tmp_path / "credential-export.jsonl"
    export.write_text(
        "user: Continue parser repair with TOKEN=abcdef1234567890 and keep tests focused.\n"
        "summary: Authorization: Bearer deadbeefcafebabefeedface was present in the old shell.\n"
        "artifact: reports/current-status.md\n"
        "unfinished: implement the source-bound private context runner.\n",
        encoding="utf-8")

    preview, status = _post("/api/continuation/preview", {
        "root": str(root), "export_path": str(export)}, state, root)

    assert status == 200
    assert "credential omitted" in json.dumps(preview["context_package"])
    intake = strict_load_json(
        (state / "artifacts" / preview["intake_ref"]).read_bytes())
    serialized = json.dumps(intake, sort_keys=True)
    assert "TOKEN=abcdef1234567890" not in serialized
    assert "deadbeefcafebabefeedface" not in serialized
    assert "selected_tasks" not in intake["context_package"]
    assert intake["context_package"]["selected_task_count"] == 2
    assert intake["context_package"]["private_context_ref"] == (
        f"continuation-private/{preview['preview_ref']}/context")
    assert any(row["code"] == "CREDENTIAL_EXCLUDED"
               for row in preview["omissions"])


def test_private_context_quarantines_credentials_but_keeps_task_context(tmp_path):
    root, state = _git_root(tmp_path), tmp_path / "state"
    (root / "slugger.py").write_text("def normalize_title(value):\n    return value\n", encoding="utf-8")
    export = tmp_path / "credential-context.jsonl"
    export.write_text(
        "user: Continue parser repair. TOKEN=abcdef1234567890 "
        "Implement normalize_title exactly.\n"
        "user: Keep slugger.py in scope; {\"api_key\": \"jsonsecretvalue12345\"} "
        "Run the existing tests.\n"
        "summary: Authorization: Bearer deadbeefcafebabefeedface was present.\n"
        "unfinished: Finish title normalization without editing tests; "
        "private_key=-----BEGIN PRIVATE KEY-----\n"
        "-----END PRIVATE KEY-----\n"
        "summary: -----BEGIN PRIVATE KEY-----\n"
        "-----END PRIVATE KEY-----\n"
        "artifact: slugger.py\n",
        encoding="utf-8")

    preview, status = _post("/api/continuation/preview", {
        "root": str(root), "export_path": str(export)}, state, root)
    assert status == 200
    context, context_status = _post("/api/continuation/context", {
        "preview_ref": preview["preview_ref"],
        "preview_sha256": preview["preview_sha256"],
        "source_state_sha256": preview["source_state_sha256"],
    }, state)

    assert context_status == 200
    goal = context["runner_context"]["goal"]
    package_text = json.dumps(context["context_package"], sort_keys=True)
    migrated = goal + package_text
    for forbidden in (
            "abcdef1234567890", "jsonsecretvalue12345",
            "deadbeefcafebabefeedface", "TOKEN=", "api_key",
            "Authorization", "Bearer", "private_key", "BEGIN PRIVATE KEY"):
        assert forbidden not in migrated
    assert "Continue parser repair" in goal
    assert "Implement normalize_title exactly" in goal
    assert "Keep slugger.py in scope" in goal
    assert "Run the existing tests" in goal
    assert "Finish title normalization without editing tests" in goal
    assert context["runner_context"]["selected_files"] == ["slugger.py"]
    assert any(row["code"] == "CREDENTIAL_EXCLUDED"
               for row in preview["omissions"])


def test_private_context_route_returns_source_bound_runner_and_refuses_drift(tmp_path):
    root, state = _tracked_dirty_root(tmp_path), tmp_path / "state"
    preview, status = _post("/api/continuation/preview", {
        "root": str(root), "export_path": str(_export(tmp_path))}, state, root)
    assert status == 200

    context, context_status = _post("/api/continuation/context", {
        "preview_ref": preview["preview_ref"],
        "preview_sha256": preview["preview_sha256"],
        "source_state_sha256": preview["source_state_sha256"],
    }, state)

    assert context_status == 200
    assert context["schema"] == "flywheel.native-continuation-private-context/v1"
    assert context["context_package"]["selected_tasks"]
    assert context["runner_context"]["root"] == str(root.resolve())
    assert "provider-neutral continuation preview" in context["runner_context"]["goal"]
    assert context["runner_context"]["selected_files"] == ["reports/current-status.md"]

    (root / "dirty.txt").write_text("changed after preview\n", encoding="utf-8")
    drift, drift_status = _post("/api/continuation/context", {
        "preview_ref": preview["preview_ref"],
        "preview_sha256": preview["preview_sha256"],
        "source_state_sha256": preview["source_state_sha256"],
    }, state)
    assert drift_status == 409 and drift["error"]["code"] == "SOURCE_DRIFT"


def test_export_state_reads_only_bounded_prefix(tmp_path, monkeypatch):
    export = tmp_path / "large-export.jsonl"
    export.write_bytes(b"summary: bounded prefix only\n" + b"x" * MAX_EXPORT_BYTES)

    def fail_read_bytes(self):
        raise AssertionError("export_state must not read the whole export")

    monkeypatch.setattr(Path, "read_bytes", fail_read_bytes)
    state, omissions = export_state(tmp_path, export)

    assert state["state"] == "read"
    assert state["truncated"] is True
    assert state["sha256"] is None
    assert state["prefix_sha256"]
    assert state["read_bytes"] == MAX_EXPORT_BYTES
    assert any(row["code"] == "EXPORT_TRUNCATED" for row in omissions)

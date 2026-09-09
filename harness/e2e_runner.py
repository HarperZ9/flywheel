"""Orchestrate versioned product E2E journeys."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat
import sys
import time
from typing import Any

from harness.cross_harness_artifacts import (
    canonical_sha256,
    create_attempt_workspace,
    preflight_artifact_root,
    snapshot_source_tree,
    validate_path_component,
)
from harness.e2e_gather_workflow import run_gather_context_flow as _run_gather_context_flow
from harness.e2e_journey_manifest import JourneyManifest, load_journey_manifest
from harness.e2e_report import JourneyRunResult, base_result, evaluate_selection, write_result_files
from harness.e2e_runtime_admission import preflight_runtime as _preflight_runtime


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _readonly_attributes(info: os.stat_result) -> int:
    attributes = int(getattr(info, "st_file_attributes", 0))
    return attributes & int(getattr(stat, "FILE_ATTRIBUTE_READONLY", 1))


def _inside(root: Path, candidate: Path) -> bool:
    try:
        root_key = os.path.normcase(os.path.normpath(str(root.resolve(strict=True))))
        candidate_key = os.path.normcase(os.path.normpath(str(candidate.resolve(strict=True))))
        return os.path.commonpath((root_key, candidate_key)) == root_key
    except (OSError, ValueError):
        return False


def _relative_to_root(root: Path, path: Path) -> str:
    resolved = path.resolve(strict=True)
    if not _inside(root, resolved):
        raise ValueError(f"manifest-owned resource outside source root: {path}")
    return resolved.relative_to(root).as_posix()


def _prefix_snapshot(snapshot: dict[str, Any], prefix: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    files: list[dict[str, Any]] = []
    directories: list[dict[str, Any]] = []
    identities: list[dict[str, Any]] = []
    for row in snapshot.get("files", []):
        updated = dict(row)
        suffix = "" if row.get("path") == "." else f"/{row.get('path')}"
        updated["path"] = f"{prefix}{suffix}"
        files.append(updated)
    for row in snapshot.get("directories", []):
        updated = dict(row)
        suffix = "" if row.get("path") == "." else f"/{row.get('path')}"
        updated["path"] = f"{prefix}{suffix}"
        directories.append(updated)
    for row in snapshot.get("identity_rows", []):
        updated = dict(row)
        suffix = "" if row.get("path") == "." else f"/{row.get('path')}"
        updated["path"] = f"{prefix}{suffix}"
        identities.append(updated)
    return files, directories, identities


def _snapshot_file(root: Path, path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    resolved = path.resolve(strict=True)
    relative = _relative_to_root(root, resolved)
    info = resolved.lstat()
    before = (info.st_size, stat.S_IMODE(info.st_mode), _readonly_attributes(info),
              info.st_dev, info.st_ino, info.st_nlink)
    if stat.S_ISLNK(info.st_mode):
        digest = hashlib.sha256(os.readlink(resolved).encode("utf-8")).hexdigest()
    elif stat.S_ISREG(info.st_mode):
        digest = _sha_file(resolved)
    else:
        raise ValueError(f"manifest-owned special file: {relative}")
    after_info = resolved.lstat()
    after = (after_info.st_size, stat.S_IMODE(after_info.st_mode), _readonly_attributes(after_info),
             after_info.st_dev, after_info.st_ino, after_info.st_nlink)
    if before != after:
        raise ValueError(f"manifest-owned concurrent mutation: {relative}")
    file_row = {"path": relative, "sha256": digest, "size": info.st_size,
                "mode": stat.S_IMODE(info.st_mode), "read_only_attributes": _readonly_attributes(info)}
    identity = {"path": relative, "kind": "file",
                "link_identity": [info.st_dev, info.st_ino, info.st_nlink]}
    return file_row, identity


def snapshot_manifest_sources(manifest: JourneyManifest) -> dict[str, Any]:
    root = manifest.repo_root.resolve(strict=True)
    files: dict[str, dict[str, Any]] = {}
    directories: dict[str, dict[str, Any]] = {}
    identities: dict[tuple[str, str], dict[str, Any]] = {}

    for relative in manifest.allowed_resource_paths:
        target = (root / Path(relative)).resolve(strict=True)
        if not _inside(root, target):
            raise ValueError(f"allowed resource path outside source root: {relative}")
        if target.is_dir():
            prefix = target.relative_to(root).as_posix()
            snap = snapshot_source_tree(target)
            prefixed_files, prefixed_dirs, prefixed_identities = _prefix_snapshot(snap, prefix)
            files.update({row["path"]: row for row in prefixed_files})
            directories.update({row["path"]: row for row in prefixed_dirs})
            identities.update({(row["path"], row["kind"]): row for row in prefixed_identities})
        elif target.is_file() or target.is_symlink():
            row, identity = _snapshot_file(root, target)
            files[row["path"]] = row
            identities[(identity["path"], identity["kind"])] = identity
        else:
            raise ValueError(f"allowed resource path unsupported: {relative}")

    manifest_path = manifest.path.resolve(strict=True)
    if not _inside(root, manifest_path):
        raise ValueError("manifest path outside source root")
    if manifest_path.is_file() or manifest_path.is_symlink():
        row, identity = _snapshot_file(root, manifest_path)
        files[row["path"]] = row
        identities[(identity["path"], identity["kind"])] = identity

    file_rows = sorted(files.values(), key=lambda row: row["path"])
    directory_rows = sorted(directories.values(), key=lambda row: row["path"])
    identity_rows = sorted(identities.values(), key=lambda row: (row["path"], row["kind"]))
    comparison = {"files": file_rows, "directories": directory_rows}
    return {"schema": "harness.cross-harness-source-snapshot/v1", **comparison,
            "sha256": canonical_sha256(comparison), "identity_rows": identity_rows,
            "identity_sha256": canonical_sha256(identity_rows)}


def _finish_blocked(manifest: JourneyManifest, run_root: Path, runtime: dict[str, Any],
                    before: dict[str, Any], source_root: Path) -> JourneyRunResult:
    result = base_result(
        manifest, run_root, runtime, platform=sys.platform, status="blocked",
        primary_outcome=str(runtime.get("reason", "runtime_blocked")))
    after = snapshot_manifest_sources(manifest)
    result.source_tree_state = "clean" if before == after else "drift"
    return write_result_files(run_root, result, manifest, before, after)


def _calibration(flow: dict[str, Any], manifest: JourneyManifest) -> tuple[str, str, dict[str, Any], dict[str, Any]]:
    expected = flow.get("expected_selection")
    oracle = evaluate_selection(flow.get("selected_payload"), manifest.oracle, expected)
    wrong_oracle = evaluate_selection(flow.get("wrong_body_payload"), manifest.oracle, expected)
    calibration = {
        "wrong_body": {"status": "pass" if wrong_oracle["status"] == "fail" else "fail",
                       "oracle_status": wrong_oracle["status"],
                       "failure_codes": wrong_oracle.get("failure_codes", [])},
        "tamper_refusal": flow.get("tamper_refusal", {"status": "not_run"}),
    }
    semantic_status = str(oracle["status"])
    if semantic_status == "pass" and all(item.get("status") == "pass" for item in calibration.values()):
        primary = "semantic_pass"
    elif semantic_status == "pass":
        primary = "control_fail"
    else:
        primary = "semantic_fail"
    return semantic_status, primary, oracle, calibration


def _execute_ready(manifest: JourneyManifest, run_root: Path, runtime: dict[str, Any],
                   before: dict[str, Any], source_root: Path) -> JourneyRunResult:
    required = [manifest.fixture_relative("source_text")]
    hashes = {relative: _sha_file(source_root / relative) for relative in required}
    attempt_dir = run_root / "attempt-001"
    workspace, _observed = create_attempt_workspace(source_root, required, hashes, attempt_dir)
    owner_state = attempt_dir / "owner-state"
    owner_state.mkdir()
    try:
        flow = _run_gather_context_flow(manifest, runtime, workspace, owner_state)
        semantic_status, primary, oracle, calibration = _calibration(flow, manifest)
        result = base_result(
            manifest, run_root, runtime, platform=sys.platform, status="completed",
            primary_outcome=primary, semantic_status=semantic_status,
            steps=list(flow.get("steps", [])), oracle=oracle, calibration=calibration,
            workspace_root=str(workspace))
    except Exception as exc:
        result = base_result(
            manifest, run_root, runtime, platform=sys.platform, status="failed",
            primary_outcome="workflow_error",
            steps=[{"id": "workflow", "status": "failed", "stderr_tail": str(exc)[-2000:]}],
            workspace_root=str(workspace))
    after = snapshot_manifest_sources(manifest)
    result.source_tree_state = "clean" if before == after else "drift"
    return write_result_files(run_root, result, manifest, before, after)


def run_journey(manifest: str | Path | JourneyManifest, *, artifact_root: str | Path,
                repo_root: str | Path | None = None, run_id: str | None = None) -> JourneyRunResult:
    loaded = manifest if isinstance(manifest, JourneyManifest) else load_journey_manifest(manifest, repo_root=repo_root)
    source_root = loaded.repo_root
    root = preflight_artifact_root(source_root, Path(artifact_root))
    name = run_id or f"{loaded.journey_id}-{int(time.time() * 1000)}"
    validate_path_component(name, "run_id")
    run_root = root / name
    if run_root.exists():
        raise ValueError("e2e run root already exists")
    run_root.mkdir(parents=True)
    before = snapshot_manifest_sources(loaded)
    runtime = _preflight_runtime(loaded)
    if runtime.get("status") != "ready":
        return _finish_blocked(loaded, run_root, runtime, before, source_root)
    return _execute_ready(loaded, run_root, runtime, before, source_root)

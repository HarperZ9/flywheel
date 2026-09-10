from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from tests.enterprise_envs.test_service_desk_review_report import _artifact_dir
from tests.enterprise_envs.test_service_desk_review_route import (
    _complete_report,
    _post,
)


def test_route_does_not_hash_swapped_source_before_private_open(
        tmp_path, monkeypatch):
    from harness.enterprise_envs import artifact_snapshot

    run_root = tmp_path / "run-root"
    artifact_dir = _artifact_dir(run_root)
    ref = artifact_dir.relative_to(run_root).as_posix()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "descriptor.json").write_text("outside", encoding="utf-8")
    original_root_identity = artifact_snapshot.root_identity
    original_snapshot_source_tree = artifact_snapshot.snapshot_source_tree
    source_snapshot_calls = []

    def guarded_snapshot_source_tree(root):
        if Path(root) == artifact_dir:
            source_snapshot_calls.append(str(root))
            raise AssertionError("source path snapshot must not run")
        return original_snapshot_source_tree(root)

    def swapping_identity(source):
        identity = original_root_identity(source)
        shutil.rmtree(source)
        try:
            os.symlink(outside, source, target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("filesystem does not permit symlink creation")
        return identity

    class Product:
        @staticmethod
        def review_artifacts(_review_dir):
            return _complete_report()

    monkeypatch.setattr(artifact_snapshot, "root_identity", swapping_identity)
    monkeypatch.setattr(
        artifact_snapshot, "snapshot_source_tree", guarded_snapshot_source_tree)
    monkeypatch.setattr(
        "harness.enterprise_envs.compat.load_service_desk_product",
        lambda: Product,
    )

    body, code = _post(run_root, {"artifact_dir_ref": ref})

    assert code == 422
    assert body["error"]["code"] == "UNSAFE_ARTIFACT_TREE"
    assert source_snapshot_calls == []


def test_route_rejects_oversize_declared_input_before_snapshot_hash(
        tmp_path, monkeypatch):
    from harness.enterprise_envs import artifact_snapshot

    run_root = tmp_path / "run-root"
    artifact_dir = run_root / "artifact"
    artifact_dir.mkdir(parents=True)
    with (artifact_dir / "descriptor.json").open("wb") as handle:
        handle.truncate(artifact_snapshot.MAX_REVIEW_FILE_BYTES + 1)
    snapshot_calls = []
    original_snapshot_source_tree = artifact_snapshot.snapshot_source_tree

    def tracked_snapshot_source_tree(root):
        snapshot_calls.append(str(root))
        return original_snapshot_source_tree(root)

    class Product:
        @staticmethod
        def review_artifacts(_review_dir):
            return _complete_report()

    monkeypatch.setattr(
        artifact_snapshot, "snapshot_source_tree", tracked_snapshot_source_tree)
    monkeypatch.setattr(
        "harness.enterprise_envs.compat.load_service_desk_product",
        lambda: Product,
    )

    body, code = _post(run_root, {"artifact_dir_ref": "artifact"})

    assert code == 422
    assert body["error"]["code"] == "UNSAFE_ARTIFACT_TREE"
    assert snapshot_calls == []

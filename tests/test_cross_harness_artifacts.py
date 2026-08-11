import hashlib
import json
import os
from pathlib import Path

import pytest

import harness.cross_harness_artifacts as artifact_module

from harness.cross_harness_artifacts import (
    bind_attempt_receipt,
    canonical_sha256,
    create_attempt_workspace,
    materialize_response_envelope,
    preflight_artifact_root,
    recheck_attempt_receipt,
    snapshot_source_tree,
    write_artifact_index,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_external_root_preflight_rejects_inside_case_and_resolved_symlink(tmp_path):
    source = tmp_path / "Source"
    source.mkdir()
    with pytest.raises(ValueError, match="artifact_root_inside_source"):
        preflight_artifact_root(source, source / "new" / "artifacts")
    if os.name == "nt":
        with pytest.raises(ValueError, match="artifact_root_inside_source"):
            preflight_artifact_root(Path(str(source).swapcase()), source / "more")
    link = tmp_path / "linked"
    try:
        link.symlink_to(source, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks unavailable")
    with pytest.raises(ValueError, match="artifact_root_inside_source"):
        preflight_artifact_root(source, link / "nested")


def test_preflight_uses_nearest_existing_parent_without_creating_root(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    proposed = tmp_path / "outside" / "new" / "run"
    assert preflight_artifact_root(source, proposed) == proposed.resolve()
    assert not (tmp_path / "outside").exists()


def test_preflight_rejects_resolved_alias_and_lexical_child_with_deterministic_seam(tmp_path, monkeypatch):
    source, outside = tmp_path / "source", tmp_path / "outside"
    source.mkdir(); outside.mkdir()
    monkeypatch.setattr(artifact_module, "_resolve_from_existing_parent", lambda _path: source.resolve())
    with pytest.raises(ValueError, match="artifact_root_inside_source"):
        preflight_artifact_root(source, outside / "alias")
    monkeypatch.setattr(artifact_module, "_resolve_from_existing_parent", lambda _path: outside.resolve())
    with pytest.raises(ValueError, match="artifact_root_inside_source"):
        preflight_artifact_root(source, source / "lexical-child")


def test_workspace_inputs_are_independent_read_only_copies_and_snapshot_is_stable(tmp_path):
    source, attempt = tmp_path / "source", tmp_path / "run" / "attempt"
    original = source / "fixtures" / "facts.json"
    original.parent.mkdir(parents=True)
    original.write_text('{"fact":1}', encoding="utf-8")
    before = snapshot_source_tree(source)
    workspace, hashes = create_attempt_workspace(
        source, ["fixtures/facts.json"], {"fixtures/facts.json": _sha(original)}, attempt
    )
    copied = workspace / "fixtures" / "facts.json"
    assert copied.read_bytes() == original.read_bytes()
    assert os.stat(copied).st_ino != os.stat(original).st_ino
    assert copied.stat().st_nlink == 1
    assert copied.stat().st_mode & 0o222 == 0
    assert hashes == {"fixtures/facts.json": _sha(original)}
    assert snapshot_source_tree(source) == before


@pytest.mark.parametrize("names", [
    ["/absolute.json"], ["../escape.json"], ["a/nested.json"], ["a\\nested.json"],
    ["same.json", "same.json"], ["Same.json", "same.json"], ["report.json:stream"],
    ["CON.json"], ["trailing.json."], ["output.txt"],
])
def test_declared_artifact_names_reject_absolute_traversal_and_duplicates(tmp_path, names):
    with pytest.raises(ValueError, match="declared artifact"):
        materialize_response_envelope('{"artifacts":{}}', names, tmp_path)


@pytest.mark.parametrize("payload", [
    '{"artifacts":{"one.json":{},"extra.md":"x"}}',
    '{"artifacts":{}}',
    '{"artifacts":{"one.json":{},"one.json":{}}}',
    '{"artifacts":{"../one.json":{}}}',
])
def test_materialization_rejects_undeclared_missing_duplicate_and_traversal_names(tmp_path, payload):
    with pytest.raises(ValueError, match="artifact"):
        materialize_response_envelope(payload, ["one.json"], tmp_path)


def test_materialization_writes_only_exact_declared_artifacts(tmp_path):
    raw, paths = materialize_response_envelope(
        '{"artifacts":{"report.json":{"value":1},"report.md":"# Result\\n"}}',
        ["report.json", "report.md"], tmp_path,
    )
    assert raw == tmp_path / "output.txt"
    assert json.loads(paths["report.json"].read_text(encoding="utf-8")) == {"value": 1}
    assert paths["report.md"].read_text(encoding="utf-8") == "# Result\n"
    assert {path.name for path in tmp_path.iterdir()} == {"output.txt", "report.json", "report.md"}


def test_receipt_binds_canonical_row_and_recheck_detects_row_or_artifact_tamper(tmp_path):
    artifact = tmp_path / "report.json"
    artifact.write_text('{"value":1}\n', encoding="utf-8")
    row = {"schema": "harness.cross-harness-task-scorecard/v1", "attempt_key": ["run", "phase", "role", "task", 1],
           "task_id": "agt-001", "execution_state": "returned", "raw_prompt_sha256": "a" * 64,
           "raw_output_sha256": _sha(artifact), "enforcement_sha256": "b" * 64,
           "tool_policy_sha256": "c" * 64, "workspace_snapshot_sha256": "d" * 64,
           "input_sha256s": {"fixture": "e" * 64}, "comparison_key": "f" * 64,
           "model_observed": "model-a", "availability_evidence": {"blocking_gates": []},
           "oracle_state": "pass", "receipt_state": "verified", "primary_outcome": "completed"}
    receipt_path = tmp_path / "receipt.json"
    receipt = bind_attempt_receipt(row, {"report.json": artifact}, receipt_path)
    assert receipt["receipt_subject_sha256"]
    assert recheck_attempt_receipt(receipt_path, row) == "verified"
    assert recheck_attempt_receipt(receipt_path, {**row, "task_id": "changed"}) == "drift"
    assert recheck_attempt_receipt(receipt_path, {**row, "oracle_state": "fail",
                                                  "primary_outcome": "oracle_fail"}) == "verified"
    for field, value in (("input_sha256s", {}), ("comparison_key", "0" * 64),
                         ("model_observed", "model-b"), ("availability_evidence", {"blocking_gates": ["stale"]})):
        assert recheck_attempt_receipt(receipt_path, {**row, field: value}) == "drift"
    artifact.write_text('{"value":2}\n', encoding="utf-8")
    assert recheck_attempt_receipt(receipt_path, row) == "drift"


def test_canonical_serializer_rejects_nonfinite_numbers():
    with pytest.raises(ValueError):
        canonical_sha256({"latency": float("nan")})


def test_artifact_index_hashes_references_but_explicitly_excludes_itself(tmp_path):
    one, two = tmp_path / "one.txt", tmp_path / "nested" / "two.txt"
    one.write_text("one", encoding="utf-8")
    two.parent.mkdir()
    two.write_text("two", encoding="utf-8")
    path = write_artifact_index(tmp_path, [one, two, one])
    index = json.loads(path.read_text(encoding="utf-8"))
    assert [row["path"] for row in index["artifacts"]] == ["nested/two.txt", "one.txt"]
    assert index["self_hash"] is None
    assert index["self_hash_reason"] == "artifact index cannot contain its own hash"

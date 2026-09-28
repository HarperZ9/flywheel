import hashlib
import json
from pathlib import Path

from harness.evidence_json import canonical_bytes, canonical_sha256
from harness.inspect_fixture_contract import (
    REQUIRED_V1_FIXTURES,
    build_contract_fixture,
    build_manifest,
    check_fixture_dir,
    manifest_identity,
)


def _raw(*, invalidated=False, version=2, scored=1):
    doc = {
        "version": version,
        "status": "success",
        "invalidated": invalidated,
        "eval": {"task": "fixture_task", "model": "mockllm/model"},
        "results": {"total_samples": 1, "completed_samples": 1, "scores": [
            {"name": "match", "scorer": "match", "scored_samples": scored, "unscored_samples": 0},
        ]},
        "samples": [{"id": "case", "epoch": 1, "scores": {"match": {"value": "C"}}}],
    }
    return json.dumps(doc, separators=(",", ":")).encode()


def _expected(*, assessment="reported", invalidated=False):
    return {
        "reported_status": "success",
        "assessment": assessment,
        "invalidated": invalidated,
        "semantic_verification": "UNVERIFIABLE",
        "counts": {"total_samples": 1, "completed_samples": 1, "observed_samples": 1},
        "scores": [{"id": "case", "epoch": 1, "scores": [{"scorer": "match", "value": "C"}]}],
    }


def _fixture_for(fixture_id: str):
    invalidated = fixture_id.endswith("invalidated")
    return build_contract_fixture(fixture_id, _raw(invalidated=invalidated))


def _expect_for(fixture_id: str):
    invalidated = fixture_id.endswith("invalidated")
    return _expected(assessment="incomplete" if invalidated else "reported", invalidated=invalidated)


def _write_set(root: Path, overrides=None):
    overrides = overrides or {}
    entries = []
    for fixture_id, rel in REQUIRED_V1_FIXTURES.items():
        fixture = overrides.get(fixture_id, {}).get("fixture", _fixture_for(fixture_id))
        expected = overrides.get(fixture_id, {}).get("expected", _expect_for(fixture_id))
        raw = canonical_bytes(fixture)
        (root / rel).write_bytes(raw)
        entries.append({"id": fixture_id, "path": rel, "fixture": fixture, "bytes": raw, "expected": expected})
    manifest = build_manifest(entries)
    (root / "manifest.json").write_bytes(canonical_bytes(manifest))
    return manifest


def _load_manifest(root: Path):
    return json.loads((root / "manifest.json").read_text(encoding="utf-8"))


def _write_manifest(root: Path, manifest):
    manifest["manifest_identity"] = manifest_identity(manifest)
    (root / "manifest.json").write_bytes(canonical_bytes(manifest))


def _fixture_report(report, fixture_id="single-success"):
    return next(item for item in report["fixtures"] if item["id"] == fixture_id)


def _kinds(problems):
    return {p["kind"] for p in problems}


def test_expected_invalidated_fixture_is_contract_success_not_semantic_pass(tmp_path):
    _write_set(tmp_path)

    report = check_fixture_dir(tmp_path)

    invalidated = _fixture_report(report, "single-invalidated")
    assert report["status"] == "ok"
    assert invalidated["status"] == "ok"
    assert invalidated["imported"]["semantic_verification"] == "UNVERIFIABLE"


def test_rewriting_projected_source_without_updating_hashes_fails(tmp_path):
    _write_set(tmp_path)
    rel = REQUIRED_V1_FIXTURES["single-success"]
    rewritten = json.loads((tmp_path / rel).read_text(encoding="utf-8"))
    rewritten["inspect_log"]["samples"][0]["scores"]["match"]["value"] = "I"
    (tmp_path / rel).write_bytes(canonical_bytes(rewritten))

    report = check_fixture_dir(tmp_path)

    problems = _kinds(_fixture_report(report)["problems"])
    assert report["status"] == "drift"
    assert "fixture_bytes_sha256_mismatch" in problems
    assert "projected_sha256_mismatch" in problems


def test_original_input_byte_hash_drift_is_reported_distinctly(tmp_path):
    _write_set(tmp_path)
    rel = REQUIRED_V1_FIXTURES["single-success"]
    changed = json.loads((tmp_path / rel).read_text(encoding="utf-8"))
    changed["source"]["original_sha256"] = "0" * 64
    (tmp_path / rel).write_bytes(canonical_bytes(changed))

    report = check_fixture_dir(tmp_path)

    assert "input_byte_sha256_mismatch" in _kinds(_fixture_report(report)["problems"])


def test_changing_expectation_changes_manifest_identity_and_is_rejected(tmp_path):
    manifest = _write_set(tmp_path)
    changed = _load_manifest(tmp_path)
    changed["fixtures"][0]["expected"]["assessment"] = "error"
    (tmp_path / "manifest.json").write_bytes(canonical_bytes(changed))

    report = check_fixture_dir(tmp_path)

    assert manifest_identity(changed) != manifest["manifest_identity"]
    assert report["status"] == "drift"
    assert report["manifest"]["problems"][0]["kind"] == "manifest_identity_mismatch"


def test_upstream_schema_version_change_cannot_silently_pass(tmp_path):
    fixture = build_contract_fixture("single-success", _raw(version=3))
    _write_set(tmp_path, {"single-success": {"fixture": fixture, "expected": _expected()}})

    report = check_fixture_dir(tmp_path)

    problems = _kinds(_fixture_report(report)["problems"])
    assert "inspect_schema_version_mismatch" in problems


def test_producer_version_change_is_reported_distinctly(tmp_path):
    fixture = build_contract_fixture("single-success", _raw(), producer_version="0.3.999")
    _write_set(tmp_path, {"single-success": {"fixture": fixture, "expected": _expected()}})

    report = check_fixture_dir(tmp_path)

    assert "producer_version_mismatch" in _kinds(_fixture_report(report)["problems"])


def test_malformed_fixture_json_is_reported_as_drift(tmp_path):
    _write_set(tmp_path)
    (tmp_path / REQUIRED_V1_FIXTURES["single-success"]).write_bytes(b'{"schema":')

    report = check_fixture_dir(tmp_path)

    assert "fixture_json_invalid" in _kinds(_fixture_report(report)["problems"])


def test_manifest_path_traversal_is_rejected_before_reading_outside_file(tmp_path):
    _write_set(tmp_path)
    outside = tmp_path.parent / "outside.fixture.json"
    outside.write_text("{}", encoding="utf-8")
    manifest = _load_manifest(tmp_path)
    manifest["fixtures"][0]["path"] = "../outside.fixture.json"
    _write_manifest(tmp_path, manifest)

    report = check_fixture_dir(tmp_path)

    problems = _kinds(_fixture_report(report)["problems"])
    assert "manifest_fixture_path_mismatch" in problems
    assert "fixture_path_rejected" not in problems


def test_empty_fixture_list_cannot_pass_with_recomputed_manifest_identity(tmp_path):
    _write_set(tmp_path)
    manifest = _load_manifest(tmp_path)
    manifest["fixtures"] = []
    _write_manifest(tmp_path, manifest)

    report = check_fixture_dir(tmp_path)

    assert report["status"] == "drift"
    assert "manifest_fixture_missing" in _kinds(report["manifest"]["problems"])


def test_required_fixture_set_rejects_missing_extra_and_duplicate_ids(tmp_path):
    scenarios = {
        "missing": ("manifest_fixture_missing", lambda m: m["fixtures"].pop()),
        "extra": ("manifest_fixture_extra", lambda m: m["fixtures"].append(dict(m["fixtures"][0], id="rogue"))),
        "duplicate": ("manifest_fixture_duplicate", lambda m: m["fixtures"].append(dict(m["fixtures"][0]))),
    }
    for name, (kind, mutate) in scenarios.items():
        root = tmp_path / name
        root.mkdir()
        _write_set(root)
        manifest = _load_manifest(root)
        mutate(manifest)
        _write_manifest(root, manifest)

        report = check_fixture_dir(root)

        assert kind in _kinds(report["manifest"]["problems"])


def test_resealed_entry_with_renamed_fixture_path_is_rejected(tmp_path):
    _write_set(tmp_path)
    rel = REQUIRED_V1_FIXTURES["single-success"]
    renamed = "renamed.fixture.json"
    (tmp_path / renamed).write_bytes((tmp_path / rel).read_bytes())
    (tmp_path / rel).unlink()
    manifest = _load_manifest(tmp_path)
    manifest["fixtures"][0]["path"] = renamed
    _write_manifest(tmp_path, manifest)

    report = check_fixture_dir(tmp_path)

    assert "manifest_fixture_path_mismatch" in _kinds(_fixture_report(report)["problems"])


def test_resealed_fixture_embedded_id_mismatch_is_rejected(tmp_path):
    _write_set(tmp_path)
    rel = REQUIRED_V1_FIXTURES["single-success"]
    changed = json.loads((tmp_path / rel).read_text(encoding="utf-8"))
    changed["id"] = "other"
    changed["fixture_sha256"] = canonical_sha256({k: v for k, v in changed.items() if k != "fixture_sha256"})
    raw = canonical_bytes(changed)
    (tmp_path / rel).write_bytes(raw)
    manifest = _load_manifest(tmp_path)
    manifest["fixtures"][0]["bytes_sha256"] = hashlib.sha256(raw).hexdigest()
    manifest["fixtures"][0]["fixture_sha256"] = changed["fixture_sha256"]
    _write_manifest(tmp_path, manifest)

    report = check_fixture_dir(tmp_path)

    assert "fixture_id_mismatch" in _kinds(_fixture_report(report)["problems"])


def test_malformed_manifest_objects_and_counts_are_typed_drift(tmp_path):
    cases = {
        "fixtures-object": ("manifest_fixtures_malformed", lambda m: m.update(fixtures={})),
        "entry-scalar": ("manifest_fixture_entry_malformed", lambda m: m.update(fixtures=[1])),
        "bad-count": ("manifest_expected_counts_malformed", lambda m: m["fixtures"][0]["expected"]["counts"].update(total_samples=True)),
    }
    for name, (kind, mutate) in cases.items():
        root = tmp_path / name
        root.mkdir()
        _write_set(root)
        manifest = _load_manifest(root)
        mutate(manifest)
        _write_manifest(root, manifest)

        report = check_fixture_dir(root)
        problems = report["manifest"]["problems"] + sum((f["problems"] for f in report["fixtures"]), [])

        assert report["status"] == "drift"
        assert kind in _kinds(problems)


def test_unsupported_safe_fixture_filesystem_fails_closed(monkeypatch, tmp_path):
    _write_set(tmp_path)
    monkeypatch.setattr("harness.inspect_fixture_contract.supported", lambda: False)

    report = check_fixture_dir(tmp_path)

    assert report["status"] == "drift"
    assert report["manifest"]["problems"] == [{"kind": "manifest_unreadable", "detail": "ValueError"}]

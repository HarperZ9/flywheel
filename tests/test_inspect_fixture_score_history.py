import json

from harness.evidence_json import canonical_bytes, canonical_sha256
from harness.inspect_fixture_contract import (
    REQUIRED_V1_FIXTURES,
    build_contract_fixture,
    build_manifest,
    check_fixture_dir,
)


def _raw(reason):
    doc = {
        "version": 2,
        "status": "success",
        "eval": {"task": "fixture_task", "model": "mockllm/model"},
        "results": {"total_samples": 1, "completed_samples": 1},
        "samples": [{
            "id": "case",
            "epoch": 1,
            "scores": {"match": {
                "value": "I",
                "history": [
                    {"value": "C"},
                    {"value": "I", "reason": reason},
                ],
            }},
        }],
    }
    return json.dumps(doc, separators=(",", ":")).encode("utf-8")


def test_fixture_projection_changes_when_only_score_history_changes():
    first = build_contract_fixture("single-success", _raw("first-review"))
    second = build_contract_fixture("single-success", _raw("second-review"))

    assert first["inspect_log"]["samples"][0]["scores"]["match"]["value"] == "I"
    assert second["inspect_log"]["samples"][0]["scores"]["match"]["value"] == "I"
    assert first["inspect_log"]["samples"][0]["scores"]["match"]["history"] != (
        second["inspect_log"]["samples"][0]["scores"]["match"]["history"]
    )
    assert canonical_sha256(first["inspect_log"]) != canonical_sha256(second["inspect_log"])


def _expected(reason):
    return {
        "reported_status": "success",
        "assessment": "reported",
        "invalidated": False,
        "semantic_verification": "UNVERIFIABLE",
        "counts": {"total_samples": 1, "completed_samples": 1, "observed_samples": 1},
        "scores": [{
            "id": "case",
            "epoch": 1,
            "scores": [{
                "scorer": "match",
                "value": "I",
                "score_history": {
                    "state": "present",
                    "events": [{"value": "C"}, {"value": "I", "reason": reason}],
                },
            }],
        }],
    }


def _write_set(root, single_fixture, single_expected):
    entries = []
    for fixture_id, rel in REQUIRED_V1_FIXTURES.items():
        fixture = single_fixture if fixture_id == "single-success" else (
            build_contract_fixture(fixture_id, _raw("baseline-review"))
        )
        expected = single_expected if fixture_id == "single-success" else _expected("baseline-review")
        raw = canonical_bytes(fixture)
        (root / rel).write_bytes(raw)
        entries.append({"id": fixture_id, "path": rel, "fixture": fixture, "bytes": raw, "expected": expected})
    manifest = build_manifest(entries)
    (root / "manifest.json").write_bytes(canonical_bytes(manifest))


def test_fixture_checker_detects_history_only_drift_with_same_final_score(tmp_path):
    changed = build_contract_fixture("single-success", _raw("second-review"))

    _write_set(tmp_path, changed, _expected("first-review"))

    report = check_fixture_dir(tmp_path)

    single = next(item for item in report["fixtures"] if item["id"] == "single-success")
    assert report["status"] == "drift"
    assert {item["kind"] for item in single["problems"]} == {"importer_score_disagreement"}

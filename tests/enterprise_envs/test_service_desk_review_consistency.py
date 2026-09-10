"""Reject internally contradictory or malformed submitted evidence, even rehashed."""
import json
import os
import shutil
import subprocess
import sys

import pytest
from tests.enterprise_envs.test_service_desk_review_report import (
    _artifact_dir, _write_json, _rehash_after_snapshot,
)
from tests.enterprise_envs.package_helpers import ROOT, product_pythonpath


@pytest.fixture(scope="module")
def baseline(tmp_path_factory):
    return _artifact_dir(tmp_path_factory.mktemp("record-review"))


@pytest.mark.parametrize("field,value,code", [
    ("authorization", False, "denied_action_recorded_as_applied"),
    ("response", 403, "unsuccessful_response_recorded_as_applied"),
    ("authorization", "true", "action_record_invalid"),
    ("response", True, "action_record_invalid"),
    ("response", "200", "action_record_invalid"),
    ("response", 600, "action_record_invalid"),
    ("mutation", 1, "action_record_invalid"),
])
def test_rehashed_record_contradictions_rejected_by_both_apis(baseline, tmp_path, field, value, code):
    from service_desk_incident_env import product
    from service_desk_incident_env.v1.store import EVENT_TAG, LOG_TAG
    from harness.enterprise_envs.digest import digest
    root = tmp_path / "copy"
    shutil.copytree(baseline, root)
    log = json.loads((root / "action-log.json").read_text())
    key = {"authorization": "allowed", "response": "status", "mutation": "applied"}[field]
    log["events"][3]["event"][field][key] = value
    for row in log["events"]:
        row["event_sha256"] = digest(EVENT_TAG, row["event"])
    _write_json(root / "action-log.json", log)
    snapshot = json.loads((root / "state-snapshot-after.json").read_text())
    snapshot["action_log_sha256"] = digest(LOG_TAG, log)
    _write_json(root / "state-snapshot-after.json", snapshot)
    _rehash_after_snapshot(root)
    report = product.review_artifacts(root)
    assert report["evidence_layers"]["source_integrity"]["observed_state"] == "pass"
    assert code in report["verification"]["failure_codes"]
    assert report["evidence_layers"]["record_consistency"]["failure_codes"] == [code]
    assert product.verify_artifacts(root) == report["verification"]
    for command in ("review", "verify"):
        run = subprocess.run([sys.executable, "-m", "service_desk_incident_env.cli", command, str(root), "--json"],
                             cwd=ROOT, env={**os.environ, "PYTHONPATH": product_pythonpath()}, capture_output=True, text=True, timeout=30)
        assert run.returncode == 1, run.stderr
        assert code in run.stdout


@pytest.mark.parametrize("name,value", [
    ("receipt.json", []), ("receipt.json", {"cases": [None]}),
    ("action-log.json", {"events": [None]}),
    ("action-log.json", {"events": [{"event": {"mutation": []}}]}),
    ("domain-state-after.json", {"tables": []}),
    ("domain-state-after.json", {"tables": {"incident": [None]}}),
    ("calibration/calibration-receipt.json", []),
])
def test_malformed_evidence_returns_failure_report(baseline, tmp_path, name, value):
    from service_desk_incident_env import product
    root = tmp_path / "copy"
    shutil.copytree(baseline, root)
    _write_json(root / name, value)
    report = product.review_artifacts(root)
    assert report["verification"]["observed_state"] == "fail"
    assert any("missing_or_invalid" in code for code in report["verification"]["failure_codes"])
    assert "Recomputed outcome" in product.render_review_html(report)


def test_positive_record_controls_and_portable_redaction(baseline):
    from service_desk_incident_env import product
    report = product.review_artifacts(baseline)
    assert report["verification"]["observed_state"] == "pass"
    assert report["evidence_layers"]["record_consistency"]["checked_record_count"] == 5
    assert report["evidence_layers"]["externally_trusted_evidence"]["observed_state"] == "not_established"
    # Baseline includes denied non-mutating requests and successful mutations.
    report["cases"][0]["case_id"] = "C:/Users/private/file.txt Bearer synthetic_REDACT_ME"
    rendered = product.render_review_html(report)
    assert "synthetic_REDACT_ME" not in rendered
    assert "C:/Users/private" not in rendered
    assert "[local path redacted]" in rendered
    assert "[credential redacted]" in rendered


@pytest.mark.parametrize("payload", [
    '{"bad": 1e309}', '{"bad": NaN}', '{"bad": "\\ud800"}', '{"same": 1, "same": 2}',
])
def test_strict_json_errors_are_reported_without_traceback(baseline, tmp_path, payload):
    from service_desk_incident_env import product
    root = tmp_path / "copy"
    shutil.copytree(baseline, root)
    (root / "domain-state-after.json").write_text(payload, encoding="utf-8")
    report = product.review_artifacts(root)
    assert report["verification"]["observed_state"] == "fail"
    assert "domain-state-after.json_missing_or_invalid" in report["verification"]["failure_codes"]


def test_report_keeps_raw_oracle_digest_valid(baseline):
    from service_desk_incident_env import product
    from harness.enterprise_envs.digest import digest
    report = product.review_artifacts(baseline)
    task = report["evidence_layers"]["synthetic_task_check"]
    assert "oracle_result_sha256" not in task
    raw = task["oracle_result"]
    subject = {key: value for key, value in raw.items() if key != "oracle_result_sha256"}
    assert raw["oracle_result_sha256"] == digest("flywheel.enterprise-env.oracle-result/v1", subject)


def test_quoted_credentials_and_unix_paths_do_not_render(baseline, tmp_path):
    from service_desk_incident_env import product
    root = tmp_path / "copy"
    shutil.copytree(baseline, root)
    source = json.loads((root / "source-basis.json").read_text())
    source["entries"][0]["id"] = {"api_key": "SYNTHETIC_ONLY_123"}
    source["entries"][0]["retrieved_at_utc"] = "/opt/research/project.md"
    _write_json(root / "source-basis.json", source)
    report = product.review_artifacts(root)
    assert report["verification"]["observed_state"] == "fail"
    rendered = product.render_review_html(report)
    assert "SYNTHETIC_ONLY_123" not in rendered
    assert "/opt/research" not in rendered
    # Also protect valid string fields carrying quoted serialized credentials.
    report = product.review_artifacts(baseline)
    report["cases"][0]["case_id"] = "{'api_key': 'SYNTHETIC_ONLY_123'} /opt/research/project.md"
    rendered = product.render_review_html(report)
    assert "SYNTHETIC_ONLY_123" not in rendered
    assert "/opt/research" not in rendered


def test_source_metadata_is_bound_to_package_manifest_contents(baseline, tmp_path):
    from service_desk_incident_env import product
    root = tmp_path / "copy"
    shutil.copytree(baseline, root)
    source = json.loads((root / "source-basis.json").read_text())
    original_marker = source["source_manifest_sha256"]
    source["entries"][0]["id"] = "fabricated_source_identity"
    _write_json(root / "source-basis.json", source)
    report = product.review_artifacts(root)
    assert source["source_manifest_sha256"] == original_marker
    assert report["verification"]["failure_codes"] == ["source_basis_content_mismatch"]
    assert report["evidence_layers"]["source_integrity"]["observed_state"] == "fail"
    checks = {row["id"]: row for row in report["evidence_layers"]["source_integrity"]["checks"]}
    assert checks["source-basis.package_sha256"]["observed_state"] == "pass"
    assert checks["source-basis.package_content_sha256"]["observed_state"] == "fail"

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from tests.enterprise_envs.package_helpers import ROOT, add_product_src, product_pythonpath


def test_review_cli_writes_portable_html_and_json_without_local_paths(tmp_path):
    """Catches review commands that only echo JSON or leak machine-local artifact paths."""
    out = tmp_path / "run"
    html_out = tmp_path / "review-output" / "review.html"
    env = {**os.environ, "PYTHONPATH": product_pythonpath()}
    e2e = subprocess.run(
        [sys.executable, "-m", "service_desk_incident_env.cli", "e2e", "--out", str(out)],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    assert e2e.returncode == 0, e2e.stderr
    artifact_dir = Path(json.loads(e2e.stdout)["artifact_dir"])

    review = subprocess.run(
        [
            sys.executable,
            "-m",
            "service_desk_incident_env.cli",
            "review",
            str(artifact_dir),
            "--html-out",
            str(html_out),
            "--json",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )

    assert review.returncode == 0, review.stderr
    doc = json.loads(review.stdout)
    assert doc["claimed_outcome"]["all_recorded_cases_passed"] is True
    assert doc["evidence_layers"]["source_integrity"]["observed_state"] == "pass"
    assert doc["evidence_layers"]["synthetic_task_check"]["observed_state"] == "pass"
    assert html_out.is_file()
    html = html_out.read_text(encoding="utf-8")
    assert "Claimed outcome" in html
    assert "Recomputed outcome" in html
    assert "Internal digest consistency is not an external signature" in html
    assert "bounded synthetic oracle" in html
    assert str(artifact_dir) not in html
    assert "Authorization: Bearer" not in html
    assert "<script" not in html.lower()
    assert " href=" not in html
    assert " src=" not in html


def test_review_report_distinguishes_altered_state_from_rehashed_false_success(tmp_path):
    """Catches reports that merge source-integrity failure with domain-oracle failure."""
    artifact_dir = _artifact_dir(tmp_path)

    altered = tmp_path / "altered-state"
    shutil.copytree(artifact_dir, altered)
    _close_target_incident(altered / "domain-state-after.json")

    self_consistent = tmp_path / "self-consistent-false-success"
    shutil.copytree(artifact_dir, self_consistent)
    _close_target_incident(self_consistent / "domain-state-after.json")
    _rehash_after_snapshot(self_consistent)

    from service_desk_incident_env import product

    altered_report = product.review_artifacts(altered)
    assert altered_report["verification"]["observed_state"] == "fail"
    assert "domain_after_sha256_mismatch" in altered_report["verification"]["failure_codes"]
    assert "target_incident_not_open" in altered_report["verification"]["failure_codes"]
    assert _check_state(altered_report, "state-snapshot-after.domain_state_sha256") == "fail"
    assert altered_report["evidence_layers"]["synthetic_task_check"]["observed_state"] == "fail"

    false_success_report = product.review_artifacts(self_consistent)
    assert false_success_report["claimed_outcome"]["all_recorded_cases_passed"] is True
    assert false_success_report["verification"]["observed_state"] == "fail"
    assert false_success_report["verification"]["failure_codes"] == ["target_incident_not_open"]
    assert false_success_report["evidence_layers"]["source_integrity"]["observed_state"] == "pass"
    assert false_success_report["evidence_layers"]["synthetic_task_check"]["observed_state"] == "fail"
    html = product.render_review_html(false_success_report)
    assert "Recorded case flags are not rerun by this review" in html
    assert "target_incident_not_open" in html


def test_review_report_fails_closed_on_missing_evidence_with_usable_codes(tmp_path):
    """Catches review paths that traceback or silently pass missing raw evidence."""
    artifact_dir = _artifact_dir(tmp_path)
    missing = tmp_path / "missing-evidence"
    shutil.copytree(artifact_dir, missing)
    (missing / "action-log.json").unlink()
    (missing / "calibration" / "calibration-receipt.json").unlink()

    from service_desk_incident_env import product

    report = product.review_artifacts(missing)
    assert report["verification"]["observed_state"] == "fail"
    assert "action-log.json_missing_or_invalid" in report["verification"]["failure_codes"]
    assert "calibration_receipt_missing_or_invalid" in report["verification"]["failure_codes"]
    html = product.render_review_html(report)
    assert "action-log.json_missing_or_invalid" in html
    assert "calibration_receipt_missing_or_invalid" in html


def test_review_html_escapes_untrusted_receipt_case_values(tmp_path):
    """Catches HTML reports that interpolate receipt-controlled strings as markup."""
    artifact_dir = _artifact_dir(tmp_path)
    injected = tmp_path / "injected"
    shutil.copytree(artifact_dir, injected)
    receipt_path = injected / "receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["cases"][0]["case_id"] = '<script>alert("owned")</script>'
    _rehash_receipt(receipt)
    _write_json(receipt_path, receipt)

    from service_desk_incident_env import product

    html = product.render_review_html(product.review_artifacts(injected))
    assert '<script>alert("owned")</script>' not in html
    assert "&lt;script&gt;alert(&quot;owned&quot;)&lt;/script&gt;" in html


def test_review_cli_refuses_to_overwrite_or_write_inside_raw_artifact_dir(tmp_path):
    """Catches report writers that mutate the original evidence bundle."""
    artifact_dir = _artifact_dir(tmp_path)
    env = {**os.environ, "PYTHONPATH": product_pythonpath()}
    raw_review = artifact_dir / "review.html"
    outside_existing = tmp_path / "existing.html"
    outside_existing.write_text("existing", encoding="utf-8")

    inside = _review_cli(artifact_dir, raw_review, env)
    overwrite = _review_cli(artifact_dir, outside_existing, env)

    assert inside.returncode == 2
    assert "html_output_inside_artifact_dir" in inside.stderr
    assert overwrite.returncode == 2
    assert "html_output_already_exists" in overwrite.stderr
    assert outside_existing.read_text(encoding="utf-8") == "existing"


def _artifact_dir(tmp_path: Path) -> Path:
    add_product_src()
    from service_desk_incident_env import product

    return Path(product.run_e2e(tmp_path / "e2e")["artifact_dir"])


def _review_cli(artifact_dir: Path, html_out: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "service_desk_incident_env.cli",
            "review",
            str(artifact_dir),
            "--html-out",
            str(html_out),
            "--json",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )


def _check_state(report: dict, check_id: str) -> str:
    for row in report["evidence_layers"]["source_integrity"]["checks"]:
        if row["id"] == check_id:
            return row["observed_state"]
    raise AssertionError(f"missing evidence check {check_id}")


def _close_target_incident(path: Path) -> None:
    doc = json.loads(path.read_text(encoding="utf-8"))
    for row in doc["tables"]["incident"]:
        if row["number"] == "INC0010001":
            row["state"] = "Closed"
    _write_json(path, doc)


def _rehash_after_snapshot(root: Path) -> None:
    from harness.enterprise_envs.digest import digest
    from service_desk_incident_env.v1.store import DOMAIN_TAG, SNAPSHOT_TAG

    after = json.loads((root / "domain-state-after.json").read_text(encoding="utf-8"))
    snapshot_path = root / "state-snapshot-after.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    snapshot["domain_state_sha256"] = digest(DOMAIN_TAG, after)
    snapshot_subject = {key: value for key, value in snapshot.items() if key != "snapshot_sha256"}
    snapshot["snapshot_sha256"] = digest(SNAPSHOT_TAG, snapshot_subject)
    _write_json(snapshot_path, snapshot)


def _rehash_receipt(receipt: dict) -> None:
    from harness.enterprise_envs.digest import digest

    subject = {key: value for key, value in receipt.items() if key != "run_receipt_sha256"}
    receipt["run_receipt_sha256"] = digest("flywheel.enterprise-env.run-receipt/v1", subject)


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")

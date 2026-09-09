import json
import subprocess
import sys
import uuid
from pathlib import Path

from tests.enterprise_envs.package_helpers import ROOT, add_product_src, product_pythonpath


def test_http_e2e_records_real_requests_state_and_hidden_control_denial(tmp_path):
    """Catches mock-only demos and agent-visible hidden control routes."""
    add_product_src()
    from service_desk_incident_env.product import run_e2e

    packet = run_e2e(tmp_path)
    cases = {case["case_id"]: case for case in packet["cases"]}

    assert cases["hidden_control_denied"]["passed"] is True
    assert cases["scripted_success"]["passed"] is True
    assert cases["concurrent_isolation"]["passed"] is True
    assert cases["double_action_idempotency"]["passed"] is True
    assert cases["reset_atomicity"]["passed"] is True
    assert cases["restart_crash_atomicity"]["passed"] is True
    assert cases["malformed_json_denied"]["passed"] is True
    assert packet["calibration"]["false_accepts"] == 0

    artifact_dir = Path(packet["artifact_dir"])
    action_log = json.loads((artifact_dir / "action-log.json").read_text(encoding="utf-8"))
    after = json.loads((artifact_dir / "domain-state-after.json").read_text(encoding="utf-8"))
    agent_view = (artifact_dir / "agent-view.json").read_text(encoding="utf-8")
    review_html = (artifact_dir / "review.html").read_text(encoding="utf-8")

    assert any(event["event"]["request"]["path_template"] == "/control/state" for event in action_log["events"])
    assert any(event["event"]["authorization"]["reason"] == "json_body_invalid" for event in action_log["events"])
    assert any(row["number"] == "INC0010001" and row["priority"] == "2" for row in after["tables"]["incident"])
    assert "Authorization: Bearer" not in agent_view
    assert "Authorization: Bearer" not in review_html
    assert "control/state" in review_html


def test_cli_e2e_writes_artifacts_without_bearer_tokens(tmp_path):
    """Catches CLI surfaces that do not exercise the real E2E runner."""
    out = tmp_path / "out"
    env = {"PYTHONPATH": product_pythonpath()}
    proc = subprocess.run(
        [sys.executable, "-m", "service_desk_incident_env.cli", "e2e", "--out", str(out)],
        cwd=ROOT,
        env={**__import__("os").environ, **env},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    packet = json.loads(proc.stdout)
    artifact_dir = Path(packet["artifact_dir"])
    assert (artifact_dir / "receipt.json").is_file()
    combined = "\n".join(path.read_text(encoding="utf-8") for path in artifact_dir.glob("*") if path.is_file())
    assert "Authorization: Bearer" not in combined


def test_secret_scan_catches_raw_token_values_and_serialized_bearers(tmp_path):
    """Catches artifact scans that only match one literal authorization header spelling."""
    from harness.enterprise_envs.receipts import scan_text_artifacts_for_secrets

    secrets = ["agent_TOKEN_VALUE_FOR_TEST", "control_TOKEN_VALUE_FOR_TEST"]
    (tmp_path / "bare-agent.txt").write_text(secrets[0], encoding="utf-8")
    (tmp_path / "bare-control.txt").write_text(secrets[1], encoding="utf-8")
    (tmp_path / "bearer.txt").write_text("bearer serialized-token", encoding="utf-8")
    (tmp_path / "json-auth.json").write_text('{"authorization":"Bearer serialized-token"}', encoding="utf-8")

    result = scan_text_artifacts_for_secrets(tmp_path, secrets)
    serialized = json.dumps(result, sort_keys=True)

    assert result["secret_values_present"] is True
    assert set(result["matching_artifacts"]) == {"bare-agent.txt", "bare-control.txt", "bearer.txt", "json-auth.json"}
    assert secrets[0] not in serialized
    assert secrets[1] not in serialized


def test_cli_rejected_output_root_returns_bounded_failure_receipt(tmp_path):
    """Catches traceback-only rejection paths and writes into the disallowed output root."""
    from harness.enterprise_envs.digest import digest

    repo = ROOT
    rejected = repo / "packages" / "service-desk-incident-env" / f"artifacts-inside-source-review-control-{uuid.uuid4().hex}"
    failure_receipt = tmp_path / "safe-failure" / "receipt.json"
    env = {"PYTHONPATH": product_pythonpath()}
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "service_desk_incident_env.cli",
            "e2e",
            "--out",
            str(rejected),
            "--failure-receipt",
            str(failure_receipt),
        ],
        cwd=repo,
        env={**__import__("os").environ, **env},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )

    assert proc.returncode == 2
    assert "Traceback" not in proc.stderr
    response = json.loads(proc.stdout)
    receipt = json.loads(failure_receipt.read_text(encoding="utf-8"))
    assert response["verdict"] == "reject"
    assert response["failure_code"] == "artifact_root_inside_source"
    assert receipt["verdict"] == "reject"
    assert receipt["rejected_artifact_root_created"] is False
    assert not rejected.exists()
    response_subject = {key: value for key, value in response.items() if key != "rejection_receipt_sha256"}
    receipt_subject = {key: value for key, value in receipt.items() if key != "rejection_receipt_sha256"}
    assert response["rejection_receipt_sha256"] == digest("flywheel.enterprise-env.rejected-output-root/v1", response_subject)
    assert receipt["rejection_receipt_sha256"] == digest("flywheel.enterprise-env.rejected-output-root/v1", receipt_subject)

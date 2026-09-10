"""Portable review report for ServiceDesk incident artifacts."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from harness.enterprise_envs.digest import digest, digest_bytes
from harness.enterprise_envs.receipts import scan_text_artifacts_for_secrets

from .v1.descriptor import ENVIRONMENT_ID, source_basis_manifest
from .v1.oracle import evaluate_task
from .review_consistency import check_record_consistency
from .review_validation import valid_doc, read_doc
from .v1.store import DOMAIN_TAG, EVENT_TAG, LOG_TAG, SNAPSHOT_TAG

REQUIRED_DOCS = (
    "descriptor.json",
    "source-basis.json",
    "domain-state-before.json",
    "state-snapshot-before.json",
    "domain-state-after.json",
    "state-snapshot-after.json",
    "action-log.json",
    "receipt.json",
)


def build_review_report(artifact_dir: Path, identity_doc: dict[str, Any]) -> dict[str, Any]:
    root = Path(artifact_dir)
    docs, load_failures = _load_docs(root)
    checks, integrity_failures = _source_integrity_checks(docs)
    calibration, calibration_failures = _calibration_review(root, docs.get("receipt.json"))
    task_check = _synthetic_task_check(docs)
    consistency = check_record_consistency(docs.get("action-log.json"))
    secret_scan = _secret_scan(root)
    secret_failures = ["secret_pattern_present"] if secret_scan.get("secret_values_present") else []
    failures = sorted(set(load_failures + integrity_failures + calibration_failures + task_check["failure_codes"] + secret_failures + consistency["failure_codes"]))
    verification = {
        "schema": "service-desk-incident-env-artifact-verification/v1",
        "artifact_dir": str(root),
        "observed_state": "fail" if failures else "pass",
        "failure_codes": failures,
        "acceptance_scope": "submitted bundle consistency and bounded task semantics only",
        "recording_authenticity": "not_established",
    }
    return {
        "schema": "service-desk-incident-env-review/v1",
        "identity": identity_doc,
        "artifact_dir": str(root),
        "artifact_label": root.name,
        "verification": verification,
        "claimed_outcome": _claimed_outcome(docs.get("receipt.json")),
        "recomputed_outcome": {
            "observed_state": verification["observed_state"],
            "failure_codes": failures,
            "basis": "source_integrity, synthetic_task_check, and record_consistency recomputed from submitted artifacts",
        },
        "evidence_layers": {
            "source_integrity": {
                "observed_state": "fail" if load_failures or integrity_failures or calibration_failures or secret_failures else "pass",
                "failure_codes": sorted(set(load_failures + integrity_failures + calibration_failures + secret_failures)),
                "checks": checks,
                "calibration": calibration,
                "secret_scan": secret_scan,
                "does_not_prove": [
                    "Internal digest consistency is not an external signature or trusted anchor.",
                    "Matching bundle digests do not prove authentic recording, provenance, or task success.",
                ],
            },
            "synthetic_task_check": task_check,
            "record_consistency": consistency,
            "externally_trusted_evidence": {
                "observed_state": "not_established",
                "reason": "No external signature, trusted timestamp, or independent evidence anchor is present in this bundle.",
            },
        },
        "source_version": _source_version(docs.get("source-basis.json")),
        "cases": _recorded_cases(docs.get("receipt.json")),
        "calibration": calibration,
        "limits": [
            "This review reads and recomputes local JSON artifacts only; it does not replay arbitrary log actions.",
            "The synthetic task check evaluates service-desk-incident/v1 state against its task contract only.",
            "A fabricated complete outcome with matching fabricated logs and rehashed metadata could satisfy the synthetic task check.",
            "Recorded case flags are not rerun by this review.",
            "The bundle does not establish production ServiceNow behavior, model success rate, external adoption, or general incident reconstruction.",
        ],
    }


def _load_docs(root: Path) -> tuple[dict[str, Any], list[str]]:
    docs: dict[str, Any] = {}
    failures: list[str] = []
    for name in REQUIRED_DOCS:
        try:
            doc = read_doc(root / name)
            if not valid_doc(name, doc):
                raise ValueError("invalid_shape")
            docs[name] = doc
        except (OSError, ValueError, UnicodeDecodeError, RecursionError):
            failures.append(f"{name}_missing_or_invalid")
    return docs, failures


def _source_integrity_checks(docs: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    checks: list[dict[str, Any]] = []
    failures: list[str] = []
    if all(name in docs for name in REQUIRED_DOCS):
        _add_check(checks, failures, "receipt.descriptor_sha256", docs["receipt.json"].get("descriptor_sha256"), digest("flywheel.enterprise-env.descriptor/v1", docs["descriptor.json"]), "descriptor_sha256_mismatch")
        _add_check(checks, failures, "receipt.source_basis_manifest_sha256", docs["receipt.json"].get("source_basis_manifest_sha256"), docs["source-basis.json"].get("source_manifest_sha256"), "source_basis_manifest_sha256_mismatch")
        _add_check(checks, failures, "state-snapshot-before.domain_state_sha256", docs["state-snapshot-before.json"].get("domain_state_sha256"), digest(DOMAIN_TAG, docs["domain-state-before.json"]), "domain_before_sha256_mismatch")
        _add_check(checks, failures, "state-snapshot-after.domain_state_sha256", docs["state-snapshot-after.json"].get("domain_state_sha256"), digest(DOMAIN_TAG, docs["domain-state-after.json"]), "domain_after_sha256_mismatch")
        for label, snapshot_name in (("before", "state-snapshot-before.json"), ("after", "state-snapshot-after.json")):
            snapshot = docs[snapshot_name]
            subject = {key: value for key, value in snapshot.items() if key != "snapshot_sha256"}
            _add_check(checks, failures, f"state-snapshot-{label}.snapshot_sha256", snapshot.get("snapshot_sha256"), digest(SNAPSHOT_TAG, subject), f"snapshot_{label}_sha256_mismatch")
        event_failures = 0
        for row in docs["action-log.json"].get("events", []):
            if row.get("event_sha256") != digest(EVENT_TAG, row.get("event")):
                event_failures += 1
        _add_check(checks, failures, "action-log.event_sha256_rows", "match" if event_failures == 0 else f"{event_failures} mismatch", "match", "action_event_sha256_mismatch")
        _add_check(checks, failures, "state-snapshot-after.action_log_sha256", docs["state-snapshot-after.json"].get("action_log_sha256"), digest(LOG_TAG, docs["action-log.json"]), "action_log_sha256_mismatch")
        receipt_subject = {key: value for key, value in docs["receipt.json"].items() if key != "run_receipt_sha256"}
        _add_check(checks, failures, "receipt.run_receipt_sha256", docs["receipt.json"].get("run_receipt_sha256"), digest("flywheel.enterprise-env.run-receipt/v1", receipt_subject), "run_receipt_sha256_mismatch")
        packaged_sha = digest_bytes((Path(__file__).resolve().parent / "v1" / "source-basis.json").read_bytes())
        _add_check(checks, failures, "source-basis.package_sha256", docs["source-basis.json"].get("source_manifest_sha256"), packaged_sha, "package_source_basis_digest_mismatch")
        content_tag = "flywheel.enterprise-env.review-source-basis/v1"
        _add_check(checks, failures, "source-basis.package_content_sha256", digest(content_tag, docs["source-basis.json"]), digest(content_tag, source_basis_manifest()), "source_basis_content_mismatch")
    return checks, failures


def _calibration_review(root: Path, receipt: Any) -> tuple[dict[str, Any], list[str]]:
    path = root / "calibration" / "calibration-receipt.json"
    try:
        calibration = read_doc(path)
        if not valid_doc("calibration-receipt.json", calibration):
            raise ValueError("invalid_shape")
    except (OSError, ValueError, UnicodeDecodeError, RecursionError):
        return {"observed_state": "fail", "failure_codes": ["calibration_receipt_missing_or_invalid"], "case_results": [], "basis": "missing_or_invalid"}, ["calibration_receipt_missing_or_invalid"]
    failures: list[str] = []
    subject = {key: value for key, value in calibration.items() if key != "calibration_sha256"}
    claimed = calibration.get("calibration_sha256")
    recomputed = digest("flywheel.enterprise-env.oracle-calibration/v1", subject)
    if claimed != recomputed or (isinstance(receipt, dict) and receipt.get("calibration", {}).get("calibration_sha256") != claimed):
        failures.append("calibration_sha256_mismatch")
    if calibration.get("false_accepts") != 0:
        failures.append("calibration_false_accepts_present")
    return {
        "observed_state": "fail" if failures else "pass",
        "failure_codes": failures,
        "false_accepts": calibration.get("false_accepts"),
        "calibration_sha256": claimed,
        "recomputed_calibration_sha256": recomputed,
        "case_results": calibration.get("case_results", []),
        "basis": "recorded calibration artifact digest checked; cases are not rerun",
    }, failures


def _synthetic_task_check(docs: dict[str, Any]) -> dict[str, Any]:
    if "domain-state-after.json" not in docs or "action-log.json" not in docs:
        return {
            "observed_state": "fail",
            "failure_codes": [],
            "basis": "missing state or action-log evidence",
            "does_not_prove": ["A missing evidence failure is reported in source_integrity."],
        }
    oracle = evaluate_task(docs["domain-state-after.json"], docs["action-log.json"])
    result = {"schema": "service-desk-task-review/v1", "observed_state": oracle["observed_state"],
              "failure_codes": oracle["failure_codes"], "oracle_result": oracle}
    result["evidence_kind"] = "task_semantics"
    result["log_origin"] = "submitted_untrusted"
    result["authorization"] = "unchecked"
    result["basis"] = "bounded synthetic oracle over submitted domain-state-after.json and action-log.json"
    result["does_not_prove"] = [
        "The oracle does not establish ground truth, authentic recording, or general incident reconstruction.",
        "Authorization and response consistency are unchecked; pass does not establish authorized execution.",
        "A fabricated complete outcome with matching fabricated logs could satisfy this check.",
    ]
    return result


def _secret_scan(root: Path) -> dict[str, Any]:
    try:
        return scan_text_artifacts_for_secrets(root, [])
    except OSError:
        return {"schema": "flywheel.enterprise-environment-secret-scan/v1", "secret_values_present": True, "matching_artifacts": [], "detector_labels": {}, "scan_error": "artifact_root_unreadable"}


def _claimed_outcome(receipt: Any) -> dict[str, Any]:
    if not isinstance(receipt, dict):
        return {"basis": "receipt missing or invalid", "all_recorded_cases_passed": False, "recorded_failed_case_ids": [], "calibration_false_accepts": "unknown"}
    cases = receipt.get("cases", []) if isinstance(receipt.get("cases"), list) else []
    failed = [str(case.get("case_id", "unknown")) for case in cases if case.get("passed") is not True]
    return {
        "basis": "receipt-recorded case flags; not accepted as semantic truth",
        "receipt_artifact_label": Path(str(receipt.get("artifact_dir", ""))).name,
        "all_recorded_cases_passed": bool(cases) and not failed,
        "recorded_case_count": len(cases),
        "recorded_failed_case_ids": failed,
        "calibration_false_accepts": receipt.get("calibration", {}).get("false_accepts", "unknown"),
        "release_boundary": receipt.get("release_boundary", {}),
    }


def _recorded_cases(receipt: Any) -> list[dict[str, Any]]:
    if not isinstance(receipt, dict) or not isinstance(receipt.get("cases"), list):
        return []
    return [{**case, "evidence_basis": "recorded_in_receipt_not_rerun"} for case in receipt["cases"] if isinstance(case, dict)]


def _source_version(source_doc: Any) -> dict[str, Any]:
    if not isinstance(source_doc, dict):
        return {"observed_state": "missing_or_invalid", "entries": []}
    entries = []
    for row in source_doc.get("entries", []):
        if isinstance(row, dict):
            entries.append({key: row.get(key) for key in ("id", "retrieved_at_utc", "body_sha256", "body_stored", "used_for")})
    return {
        "environment_id": ENVIRONMENT_ID,
        "created_at_utc": source_doc.get("created_at_utc"),
        "source_manifest_sha256": source_doc.get("source_manifest_sha256", "unknown"),
        "entries": entries,
    }


def _add_check(checks: list[dict[str, Any]], failures: list[str], check_id: str, claimed: Any, recomputed: Any, failure_code: str) -> None:
    state = "pass" if claimed == recomputed else "fail"
    checks.append({"id": check_id, "observed_state": state, "claimed": claimed, "recomputed": recomputed, "failure_code": None if state == "pass" else failure_code})
    if state == "fail":
        failures.append(failure_code)

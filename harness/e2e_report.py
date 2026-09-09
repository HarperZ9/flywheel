"""Result and artifact reporting for product E2E journeys."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any

from harness.cross_harness_artifacts import bind_attempt_receipt, write_artifact_index
from harness.cross_harness_run_seal import write_json
from harness.cross_harness_types import sanitize_evidence
from harness.e2e_journey_manifest import RUN_SCHEMA, JourneyManifest

DOES_NOT_PROVE = [
    "source truth", "claim support", "semantic completeness", "model quality", "all product commands",
]


@dataclass
class JourneyRunResult:
    schema: str
    journey_id: str
    product: str
    status: str
    primary_outcome: str
    semantic_status: str
    runtime: dict[str, Any]
    platform: str
    source: str
    steps: list[dict[str, Any]]
    oracle: dict[str, Any]
    calibration: dict[str, Any]
    artifacts: dict[str, str]
    workspace_root: str
    run_root: str
    source_tree_state: str
    does_not_prove: list[str]

    def to_dict(self) -> dict[str, Any]:
        return sanitize_evidence({
            "schema": self.schema, "journey_id": self.journey_id, "product": self.product,
            "status": self.status, "primary_outcome": self.primary_outcome,
            "semantic_status": self.semantic_status, "runtime": self.runtime, "platform": self.platform,
            "source": self.source, "steps": self.steps, "oracle": self.oracle,
            "calibration": self.calibration, "artifacts": self.artifacts,
            "workspace_root": self.workspace_root, "run_root": self.run_root,
            "source_tree_state": self.source_tree_state, "does_not_prove": self.does_not_prove,
        })


def evaluate_selection(payload: dict[str, Any] | None, oracle: dict[str, Any],
                       expected: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"status": "not_run", "failure_codes": ["payload_missing"]}
    failures: list[str] = []
    texts = [str(item.get("text", "")) for item in payload.get("selections", []) if isinstance(item, dict)]
    combined = "\n".join(texts)
    if payload.get("schema") != "gather.readable-context/v1":
        failures.append("schema_mismatch")
    if str(oracle["include_text"]) not in combined:
        failures.append("include_text_missing")
    if str(oracle["exclude_text"]) in combined:
        failures.append("exclude_text_present")
    observed_sha = hashlib.sha256(combined.encode("utf-8")).hexdigest()
    expected_text = str((expected or {}).get("text", ""))
    expected_sha = str((expected or {}).get("sha256", ""))
    if expected_text and combined != expected_text:
        failures.append("selection_text_mismatch")
    if expected_sha and observed_sha != expected_sha:
        failures.append("selection_sha256_mismatch")
    digest = payload.get("selection_digest")
    if not isinstance(digest, str) or len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        failures.append("selection_digest_invalid")
    if payload.get("verified") is not True:
        failures.append("selection_not_verified")
    return {"status": "fail" if failures else "pass", "failure_codes": failures,
            "selected_text_chars": len(combined), "selection_digest": digest if isinstance(digest, str) else "",
            "expected_selection_sha256": expected_sha, "observed_selection_sha256": observed_sha,
            "expected_range": {key: (expected or {}).get(key) for key in ("start", "limit")}}


def base_result(manifest: JourneyManifest, run_root: Path, runtime: dict[str, Any], *,
                platform: str, status: str, primary_outcome: str,
                semantic_status: str = "not_run", steps: list[dict[str, Any]] | None = None,
                oracle: dict[str, Any] | None = None, calibration: dict[str, Any] | None = None,
                workspace_root: str = "", source_tree_state: str = "unrecorded") -> JourneyRunResult:
    return JourneyRunResult(
        schema=RUN_SCHEMA, journey_id=manifest.journey_id, product=manifest.product,
        status=status, primary_outcome=primary_outcome, semantic_status=semantic_status,
        runtime=runtime, platform=platform, source=str(runtime.get("source", "unknown")),
        steps=steps or [], oracle=oracle or {"status": "not_run"}, calibration=calibration or {},
        artifacts={}, workspace_root=workspace_root, run_root=str(run_root),
        source_tree_state=source_tree_state, does_not_prove=list(DOES_NOT_PROVE),
    )


def write_result_files(run_root: Path, result: JourneyRunResult, manifest: JourneyManifest,
                       before: dict[str, Any], after: dict[str, Any]) -> JourneyRunResult:
    manifest_path = run_root / "manifest.json"
    steps_path = run_root / "steps.json"
    oracle_path = run_root / "oracle.json"
    calibration_path = run_root / "calibration.json"
    snapshots_path = run_root / "source-snapshots.json"
    result_path = run_root / "run-result.json"
    receipt_path = run_root / "receipt.json"
    index_path = run_root / "artifact-index.json"
    result.artifacts.update({
        "manifest": str(manifest_path), "steps": str(steps_path), "oracle": str(oracle_path),
        "calibration": str(calibration_path), "source_snapshots": str(snapshots_path),
        "run_result": str(result_path), "receipt": str(receipt_path), "artifact_index": str(index_path),
    })
    write_json(manifest_path, manifest.to_dict())
    write_json(steps_path, result.steps)
    write_json(oracle_path, result.oracle)
    write_json(calibration_path, result.calibration)
    write_json(snapshots_path, {"schema": "flywheel.product-e2e-source-snapshots/v1",
                                "before": before, "after": after, "state": result.source_tree_state})
    write_json(result_path, result.to_dict())
    receipt = bind_attempt_receipt(result.to_dict(), {
        "manifest.json": manifest_path, "steps.json": steps_path, "oracle.json": oracle_path,
        "calibration.json": calibration_path, "source-snapshots.json": snapshots_path,
        "run-result.json": result_path,
    }, receipt_path)
    result.artifacts["receipt_subject_sha256"] = str(receipt["receipt_subject_sha256"])
    write_artifact_index(run_root, [manifest_path, steps_path, oracle_path, calibration_path,
                                    snapshots_path, result_path, receipt_path])
    return result


def artifact_hash_manifest(paths: list[Path]) -> dict[str, Any]:
    rows = []
    for path in paths:
        digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        rows.append({"path": str(path), "sha256": digest})
    return {"schema": "flywheel.product-e2e-artifact-hash-manifest/v1", "artifacts": rows}

from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


PRECOMMIT_CANONICAL_REF = "fca252d59efdb627549e5677263c69709590c982"
MACOS_CANONICAL_REF = "6bcda970fde272b06cff0d8f397224dbac96d7ad"


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name}: expected a JSON object")
    return value


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp is not timezone-aware: {value!r}")
    return parsed


def duration_seconds(start: str, end: str) -> int:
    seconds = round((_parse_timestamp(end) - _parse_timestamp(start)).total_seconds())
    if seconds < 0:
        raise ValueError(f"end timestamp precedes start timestamp: {start!r} -> {end!r}")
    return seconds


def nearest_rank_percentile(values: Iterable[int], percentile: float) -> int:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("percentile requires at least one value")
    if not 0 < percentile <= 1:
        raise ValueError("percentile must be in (0, 1]")
    return ordered[math.ceil(percentile * len(ordered)) - 1]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_blob_sha(path: Path) -> str:
    body = path.read_bytes()
    # Git's object identity uses this SHA-1 framing. The receipt separately
    # records SHA-256 for content integrity; this is not a cryptographic choice.
    return hashlib.sha1(b"blob " + str(len(body)).encode("ascii") + b"\0" + body).hexdigest()


def _expand_run_records(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    field_map = snapshot.get("field_map")
    records = snapshot.get("records")
    if not isinstance(records, list):
        raise ValueError("run snapshot records must be a list")
    if not field_map:
        expanded = records
    else:
        expanded = [{field_map.get(key, key): value for key, value in row.items()} for row in records]
    ids = [row["id"] for row in expanded]
    if len(ids) != len(set(ids)):
        raise ValueError("run snapshot contains duplicate run ids")
    return expanded


def _elapsed_summary(values: list[int]) -> dict[str, Any]:
    if not values:
        raise ValueError("elapsed summary requires at least one value")
    return {
        "definition": "updated_at minus run_started_at",
        "maximum": max(values),
        "median": float(statistics.median(values)),
        "minimum": min(values),
        "p90_method": "nearest-rank",
        "p90": nearest_rank_percentile(values, 0.9),
        "sum": sum(values),
    }


def _find_run(records: list[dict[str, Any]], run_id: int) -> dict[str, Any]:
    matches = [row for row in records if row["id"] == run_id]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one record for run {run_id}, found {len(matches)}")
    return matches[0]


def _find_job(snapshot: dict[str, Any], name: str) -> dict[str, Any]:
    matches = [job for job in snapshot["jobs"] if job["name"] == name]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one job named {name!r}, found {len(matches)}")
    return matches[0]


def _find_step(job: dict[str, Any], name_prefix: str) -> dict[str, Any]:
    matches = [step for step in job["steps"] if step["name"].startswith(name_prefix)]
    if len(matches) != 1:
        raise ValueError(
            f"expected exactly one step starting with {name_prefix!r}, found {len(matches)}"
        )
    return matches[0]


def _precommit_run_detail(
    run_records: list[dict[str, Any]],
    job_snapshot: dict[str, Any],
    run_metadata: dict[str, Any],
) -> dict[str, Any]:
    run_id = int(job_snapshot["run_id"])
    run = _find_run(run_records, run_id)
    job = _find_job(job_snapshot, "pre-commit")
    action = _find_step(job, "Run pre-commit/action@")
    return {
        "run_id": run_id,
        "head_sha": run_metadata["head_sha"],
        "workflow_id": run_metadata["workflow_id"],
        "workflow_path": run_metadata["path"],
        "workflow_conclusion": run["conclusion"],
        "workflow_elapsed_seconds": duration_seconds(run["run_started_at"], run["updated_at"]),
        "job_conclusion": job["conclusion"],
        "job_elapsed_seconds": duration_seconds(job["started_at"], job["completed_at"]),
        "precommit_action_elapsed_seconds": duration_seconds(
            action["started_at"], action["completed_at"]
        ),
        "runner_labels": sorted(job["labels"]),
        "run_url": f"https://github.com/vllm-project/vllm/actions/runs/{run_id}",
        "jobs_api_url": job_snapshot["endpoint"],
    }


def _macos_job_detail(job: dict[str, Any]) -> dict[str, Any]:
    build = _find_step(job, "Install dependencies and build vLLM")
    smoke = _find_step(job, "Smoke test vllm serve")
    return {
        "job_conclusion": job["conclusion"],
        "job_elapsed_seconds": duration_seconds(job["started_at"], job["completed_at"]),
        "build_elapsed_seconds": duration_seconds(build["started_at"], build["completed_at"]),
        "smoke_elapsed_seconds": duration_seconds(smoke["started_at"], smoke["completed_at"]),
        "runner_labels": sorted(job["labels"]),
        "job_url": job["html_url"],
    }


def _workflow_provenance(data_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    by_id = {item["workflow_id"]: item for item in manifest["workflows"]}
    precommit = by_id[137737330]
    macos = by_id[207055592]
    for workflow, expected_ref in (
        (precommit, PRECOMMIT_CANONICAL_REF),
        (macos, MACOS_CANONICAL_REF),
    ):
        captures = workflow.get("captures")
        if not isinstance(captures, list) or not captures:
            raise ValueError("workflow manifest canonical capture ref has no captures")
        refs = [capture.get("ref") for capture in captures]
        if len(refs) != len(set(refs)):
            raise ValueError("workflow manifest has duplicate capture refs")
        if workflow.get("canonical_capture_ref") != expected_ref or refs[0] != expected_ref:
            raise ValueError("workflow manifest canonical capture ref does not match the source pin")
        expected_url = (
            f"https://raw.githubusercontent.com/vllm-project/vllm/{expected_ref}/"
            f"{workflow['path']}"
        )
        if captures[0].get("download_url") != expected_url:
            raise ValueError("workflow manifest canonical capture ref URL mismatch")
    precommit_source = data_dir / "pre-commit.yml"
    macos_source = data_dir / "macos-smoke-test.yml"

    precommit_blobs = {capture["git_blob_sha"] for capture in precommit["captures"]}
    if precommit_blobs != {_git_blob_sha(precommit_source)}:
        raise ValueError("pre-commit workflow capture does not match its pinned Git blob")
    if {capture["size"] for capture in precommit["captures"]} != {precommit_source.stat().st_size}:
        raise ValueError("pre-commit workflow capture size mismatch")
    if _git_blob_sha(macos_source) != macos["captures"][0]["git_blob_sha"]:
        raise ValueError("macOS workflow capture does not match its pinned Git blob")

    precommit_text = precommit_source.read_text(encoding="utf-8")
    macos_text = macos_source.read_text(encoding="utf-8")
    for needle in (
        "cancel-in-progress: ${{ github.event_name == 'pull_request' }}",
        "runs-on: [self-hosted, linux, x64, vllm-runners]",
        "extra_args: --all-files --hook-stage manual",
    ):
        if needle not in precommit_text:
            raise ValueError(f"pinned pre-commit workflow is missing expected text: {needle}")
    for needle in (
        "- cron: '30 2 * * *'",
        "- os: macos-26",
        "required: false",
        "continue-on-error: ${{ !matrix.required }}",
        "enable-cache: true",
    ):
        if needle not in macos_text:
            raise ValueError(f"pinned macOS workflow is missing expected text: {needle}")

    return {
        "precommit": {
            "workflow_id": 137737330,
            "path": precommit["path"],
            "canonical_capture_ref": precommit["canonical_capture_ref"],
            "git_blob_sha": next(iter(precommit_blobs)),
            "source_sha256": _sha256(precommit_source),
            "representative_run_refs": [
                capture["ref"] for capture in precommit["captures"][1:]
            ],
            "source_url": precommit["captures"][0]["download_url"],
        },
        "macos": {
            "workflow_id": 207055592,
            "path": macos["path"],
            "canonical_capture_ref": macos["canonical_capture_ref"],
            "git_blob_sha": macos["captures"][0]["git_blob_sha"],
            "source_sha256": _sha256(macos_source),
            "source_url": macos["captures"][0]["download_url"],
        },
    }


def _bind_representative_runs(
    snapshot: dict[str, Any],
    manifest: dict[str, Any],
    workflows: dict[str, Any],
    precommit_runs: list[dict[str, Any]],
    macos_runs: list[dict[str, Any]],
) -> dict[int, dict[str, Any]]:
    if snapshot.get("schema") != "github-actions-representative-runs/1":
        raise ValueError("representative run snapshot schema mismatch")
    runs = snapshot.get("runs")
    if not isinstance(runs, list):
        raise ValueError("representative run snapshot must contain a runs list")
    run_ids = [int(run["id"]) for run in runs]
    if len(run_ids) != len(set(run_ids)):
        raise ValueError("duplicate representative run id")
    by_id = {int(run["id"]): run for run in runs}
    expected_ids = {29857602498, 29858770343, 29799057515}
    if set(by_id) != expected_ids:
        raise ValueError("representative run ids do not match the receipt contract")

    manifest_by_id = {item["workflow_id"]: item for item in manifest["workflows"]}
    contracts = {
        29857602498: ("precommit", precommit_runs),
        29858770343: ("precommit", precommit_runs),
        29799057515: ("macos", macos_runs),
    }
    for run_id, (workflow_name, aggregate_records) in contracts.items():
        run = by_id[run_id]
        workflow = workflows[workflow_name]
        if run["workflow_id"] != workflow["workflow_id"]:
            raise ValueError(f"run {run_id} workflow id mismatch")
        if run["path"] != workflow["path"]:
            raise ValueError(f"run {run_id} workflow path mismatch")
        captures = manifest_by_id[run["workflow_id"]]["captures"]
        matching_capture = [capture for capture in captures if capture["ref"] == run["head_sha"]]
        if len(matching_capture) != 1:
            raise ValueError(f"run {run_id} head_sha is not pinned in the workflow manifest")
        if matching_capture[0]["git_blob_sha"] != workflow["git_blob_sha"]:
            raise ValueError(f"run {run_id} head_sha is bound to a different workflow Git blob")
        aggregate = _find_run(aggregate_records, run_id)
        for field in ("event", "status", "conclusion", "run_started_at", "updated_at"):
            if run[field] != aggregate[field]:
                raise ValueError(f"run {run_id} {field} differs from the aggregate snapshot")
    return by_id


def analyze(data_dir: Path) -> dict[str, Any]:
    data_dir = Path(data_dir)
    filenames = (
        "macos-jobs.json",
        "macos-runs.json",
        "macos-smoke-test.yml",
        "pre-commit.yml",
        "precommit-cancelled-jobs.json",
        "precommit-runs.json",
        "precommit-success-jobs.json",
        "representative-runs.json",
        "workflow-manifest.json",
    )
    for filename in filenames:
        if not (data_dir / filename).is_file():
            raise FileNotFoundError(data_dir / filename)

    precommit_snapshot = _read_json(data_dir / "precommit-runs.json")
    precommit_runs = _expand_run_records(precommit_snapshot)
    completed_precommit = [run for run in precommit_runs if run["status"] == "completed"]
    precommit_elapsed = [
        duration_seconds(run["run_started_at"], run["updated_at"])
        for run in completed_precommit
    ]
    success_jobs = _read_json(data_dir / "precommit-success-jobs.json")
    cancelled_jobs = _read_json(data_dir / "precommit-cancelled-jobs.json")

    macos_snapshot = _read_json(data_dir / "macos-runs.json")
    macos_runs = _expand_run_records(macos_snapshot)
    completed_macos = [run for run in macos_runs if run["status"] == "completed"]
    macos_elapsed = [
        duration_seconds(run["run_started_at"], run["updated_at"])
        for run in completed_macos
    ]
    macos_jobs = _read_json(data_dir / "macos-jobs.json")
    macos_15 = _find_job(macos_jobs, "macos-m1-smoke-test (macos-15)")
    macos_26 = _find_job(macos_jobs, "macos-m1-smoke-test (macos-26)")
    representative_macos = _find_run(macos_runs, int(macos_jobs["run_id"]))

    manifest = _read_json(data_dir / "workflow-manifest.json")
    input_hashes = {filename: _sha256(data_dir / filename) for filename in filenames}
    workflows = _workflow_provenance(data_dir, manifest)
    representative_snapshot = _read_json(data_dir / "representative-runs.json")
    representative_runs = _bind_representative_runs(
        representative_snapshot, manifest, workflows, precommit_runs, macos_runs
    )

    return {
        "schema": "vllm-ci-efficiency-analysis/1",
        "repository": "vllm-project/vllm",
        "measurement_contract": {
            "run_elapsed_seconds": (
                "GitHub run updated_at minus run_started_at; end-to-end wall-clock elapsed, "
                "not billed runner time"
            ),
            "job_elapsed_seconds": (
                "GitHub job completed_at minus started_at; wall-clock job elapsed, not a "
                "billing record"
            ),
            "step_elapsed_seconds": (
                "GitHub step completed_at minus started_at; rounded to whole seconds"
            ),
            "billed_runner_time": "not present in the captured public API fields",
            "estimate_policy": "no efficiency or billing estimate is calculated",
        },
        "provenance": {
            "inputs": input_hashes,
            "workflows": workflows,
            "representative_runs": {
                str(run_id): {
                    "workflow_id": run["workflow_id"],
                    "workflow_path": run["path"],
                    "head_sha": run["head_sha"],
                    "run_url": run["html_url"],
                }
                for run_id, run in sorted(representative_runs.items())
            },
            "snapshot_urls": {
                "precommit_runs": precommit_snapshot["endpoint"],
                "precommit_success_jobs": success_jobs["endpoint"],
                "precommit_cancelled_jobs": cancelled_jobs["endpoint"],
                "macos_runs": macos_snapshot["endpoint"],
                "macos_jobs": macos_jobs["endpoint"],
                "representative_runs": (
                    "https://api.github.com/repos/vllm-project/vllm/actions/runs/{run_id}"
                ),
            },
            "retrieved_at": {
                "precommit_runs": precommit_snapshot["retrieved_at"],
                "precommit_success_jobs": success_jobs["retrieved_at"],
                "precommit_cancelled_jobs": cancelled_jobs["retrieved_at"],
                "macos_runs": macos_snapshot["retrieved_at"],
                "macos_jobs": macos_jobs["retrieved_at"],
                "representative_runs": representative_snapshot["retrieved_at"],
                "workflow_manifest": manifest["retrieved_at"],
            },
        },
        "precommit": {
            "workflow_id": 137737330,
            "sample_size": len(precommit_runs),
            "completed_records": len(completed_precommit),
            "conclusions": dict(sorted(Counter(run["conclusion"] for run in completed_precommit).items())),
            "run_elapsed_seconds": _elapsed_summary(precommit_elapsed),
            "representative_runs": {
                "successful_workflow": _precommit_run_detail(
                    precommit_runs, success_jobs, representative_runs[29857602498]
                ),
                "cancelled_workflow": _precommit_run_detail(
                    precommit_runs, cancelled_jobs, representative_runs[29858770343]
                ),
            },
            "workflow_controls": {
                "pull_request_cancel_in_progress": True,
                "runner": ["self-hosted", "linux", "x64", "vllm-runners"],
                "precommit_scope": "--all-files --hook-stage manual",
            },
            "billed_runner_time_seconds": None,
            "attributable_avoidable_time_seconds": None,
        },
        "macos": {
            "workflow_id": 207055592,
            "sample_size": len(macos_runs),
            "completed_records": len(completed_macos),
            "scheduled_records": sum(run["event"] == "schedule" for run in macos_runs),
            "conclusions": dict(sorted(Counter(run["conclusion"] for run in completed_macos).items())),
            "run_elapsed_seconds": _elapsed_summary(macos_elapsed),
            "representative_run": {
                "run_id": representative_macos["id"],
                "workflow_conclusion": representative_macos["conclusion"],
                "workflow_elapsed_seconds": duration_seconds(
                    representative_macos["run_started_at"], representative_macos["updated_at"]
                ),
                "head_sha": representative_runs[29799057515]["head_sha"],
                "workflow_id": representative_runs[29799057515]["workflow_id"],
                "workflow_path": representative_runs[29799057515]["path"],
                "run_url": representative_macos["html_url"],
                "parallel_job_overlap_seconds": duration_seconds(
                    max(macos_15["started_at"], macos_26["started_at"]),
                    min(macos_15["completed_at"], macos_26["completed_at"]),
                ),
                "jobs": {
                    "macos-15": _macos_job_detail(macos_15),
                    "macos-26": _macos_job_detail(macos_26),
                },
            },
            "workflow_controls": {
                "schedule": "daily at 02:30 UTC",
                "macos-15_required": True,
                "macos-26_required": False,
                "macos-26_continue_on_error": True,
                "uv_cache_enabled": True,
            },
            "billed_runner_time_seconds": None,
            "attributable_avoidable_time_seconds": None,
        },
        "claims": [
            {
                "id": "precommit-snapshot",
                "state": "verified",
                "text": (
                    "The pinned latest-100 pre-commit snapshot contains 35 cancelled outcomes; "
                    "this is an outcome count, not a billed-time or waste estimate."
                ),
                "estimated_savings_seconds": None,
            },
            {
                "id": "cancelled-run-job",
                "state": "verified",
                "text": (
                    "Run 29858770343 concluded cancelled while its self-hosted pre-commit job "
                    "concluded success after 263 elapsed seconds, including 245 seconds in the "
                    "pre-commit action."
                ),
                "estimated_savings_seconds": None,
            },
            {
                "id": "cancellation-experiment",
                "state": "inference",
                "text": (
                    "Instrumenting cancellation request, runner receipt, process exit, and job "
                    "completion timestamps could determine whether runner occupancy is reducible."
                ),
                "estimated_savings_seconds": None,
            },
            {
                "id": "macos-parallel-preview",
                "state": "verified",
                "text": (
                    "In run 29799057515, required macos-15 and non-blocking macos-26 jobs ran "
                    "in parallel for 1326 and 1329 elapsed seconds."
                ),
                "estimated_savings_seconds": None,
            },
            {
                "id": "macos-cadence-experiment",
                "state": "inference",
                "text": (
                    "A controlled cadence experiment for the preview macos-26 lane could measure "
                    "coverage value against runner occupancy before any schedule change."
                ),
                "estimated_savings_seconds": None,
            },
            {
                "id": "billing-and-savings",
                "state": "unknown",
                "text": (
                    "Billed minutes, queue time decomposition, self-hosted capacity cost, and "
                    "attributable avoidable time are not established by these public snapshots."
                ),
                "estimated_savings_seconds": None,
            },
        ],
        "limitations": [
            "The latest-N API windows are a time-bounded convenience sample, not a randomized sample.",
            "The workflow Git blob was bound to the representative runs, not to every head in the 100-run aggregate window.",
            "updated_at minus run_started_at includes more than runner execution and cannot be billed as job time.",
            "Job and step timestamps have one-second granularity in these captures.",
            "A cancelled workflow with a successful job does not by itself prove a cancellation defect or avoidable work.",
            "macos-15 and macos-26 elapsed times overlap; adding them is not a workflow latency estimate.",
            "No proposed policy change was executed, so no savings, regression rate, or coverage impact was measured.",
        ],
    }

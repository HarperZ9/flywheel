"""pysyft_adapter.py -- read one finished PySyft job into receipt inputs.

The thin seam between PySyft's on-disk layout and `job_result_receipt`. It is the
only Flywheel module that touches syft, and it imports nothing from it: it works on
the `JobClient` the caller already built, so Flywheel's core and the stranger's
verifier never depend on syft.

It reads, for one job the data owner approved and ran:
- the submission folder (code/, run.sh, config.yaml) the runner checked;
- staging/.../submission.json, the record PySyft wrote at arrival and approval
  (`received_hash`, `approved_hash`, `approved_by`, `approved_at`,
  `approval_method`), kept as raw bytes so the receipt can bind its SHA-256;
- the job's state (status, reviewer, review reason) through syft-job's own reader;
- review/.../outputs/results.jsonl, the per-item rows the job wrote.

Layout and field names are from syft-job 0.1.41 at OpenMined/PySyft commit
36e65162ad2cfbae66d714db8d5c711e19a3a185. syft-job 0.1.40 on PyPI predates the
approved hash and is not supported: `collect` refuses a record with none.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .pysyft_job_hash import submission_hash


class PySyftAdapterError(RuntimeError):
    """syft-job is missing, or the job is not an approved, finished one."""


@dataclass(frozen=True)
class JobRecordPaths:
    submission_dir: Path
    submission_record: Path
    results: Path


def _find(client, job_name: str):
    matches = [j for j in client.jobs if j.name == job_name]
    if len(matches) != 1:
        raise PySyftAdapterError(f"expected one job named {job_name!r}, found {len(matches)}")
    return matches[0]._ref  # syft-job exposes no public accessor for the JobRef


def _state_fields(state) -> dict:
    def iso(v):
        return v.isoformat() if v is not None else None
    return {"status": getattr(state.status, "value", state.status),
            "review_reason": state.review_reason, "approved_by": state.approved_by,
            "completed_at": iso(getattr(state, "completed_at", None))}


def collect(client, job_name: str) -> tuple:
    """(paths, inputs) for one job, read through the data owner's syft-job
    `JobClient`. `inputs` are keyword arguments for `build_body`, minus the
    caller's nonce, issue time and commitments. Refuses a job that is not done,
    has no approved hash, or whose folder no longer matches it."""
    ref = _find(client, job_name)
    manager = client.manager
    paths = JobRecordPaths(submission_dir=manager.submission_dir(ref),
                           submission_record=manager.submission_record_path(ref),
                           results=manager.review_dir(ref) / "outputs" / "results.jsonl")
    review = _state_fields(manager.read_state(ref))
    if review["status"] != "done":
        raise PySyftAdapterError(f"job status is {review['status']!r}, not 'done'")
    record_bytes = paths.submission_record.read_bytes()
    approved = json.loads(record_bytes.decode("utf-8")).get("approved_hash")
    if not approved:
        raise PySyftAdapterError("no approved_hash: syft-job older than PR #9536, or not approved")
    if submission_hash(paths.submission_dir) != approved:
        raise PySyftAdapterError("submission folder no longer matches the approved hash")
    inputs = {"job_name": job_name, "submission_record": record_bytes, "review": review,
              "results": paths.results.read_bytes()}
    return paths, inputs

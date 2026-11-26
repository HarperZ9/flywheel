"""Parallel Colab Pro+ GPU/TPU job manifest generator with compute-cap and data-gate guards."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

COLAB_JOB_SCHEMA = "colab-job/1"
STAGE1_MIN_PHYSAI_TRAJECTORIES = 200_000

ACCELERATOR_RATES: dict[str, float] = {
    "T4": 1.96,
    "L4": 4.82,
    "A100": 11.77,
    "H100": 19.50,
    "v5e-1": 3.20,
    "v6e-1": 6.50,
}

COLAB_PROFILES: dict[str, dict[str, Any]] = {
    "stage1_data_curation": {
        "stage": "stage1",
        "requires_data_gate": False,
        "default_accelerator": "L4",
        "entrypoint": "python -m flywheel.stage1_curate --shard {shard} --shards {total}",
        "outputs": ["curated_shard.jsonl", "decontam_report.json", "engine_receipt.json"],
    },
    "gather_deconstruct_batch": {
        "stage": "stage1",
        "requires_data_gate": False,
        "default_accelerator": "L4",
        "entrypoint": "gather deconstruct {input_dir} --out {out_dir} --json",
        "outputs": ["media_deconstruction.json", "engine_receipt.json"],
    },
    "physai_trajectories": {
        "stage": "stage1",
        "requires_data_gate": False,
        "default_accelerator": "A100",
        "entrypoint": "python -m world.physai.rollout --trajectories {trajectories} --shard {shard}",
        "outputs": ["physai_rollouts.jsonl", "contact_invariants.json", "engine_receipt.json"],
    },
    "gpu_kernel_bench": {
        "stage": "stage1",
        "requires_data_gate": False,
        "default_accelerator": "H100",
        "entrypoint": "python bench_kernels.py --accelerator {accelerator} --json",
        "outputs": ["kernel_bench.json", "engine_receipt.json"],
    },
    "frontier_pretraining": {
        "stage": "stage2",
        "requires_data_gate": True,
        "default_accelerator": "H100",
        "entrypoint": "python train_frontier.py --stage2-verified-manifest {manifest}",
        "outputs": ["checkpoint.safetensors", "eval_receipt.json", "engine_receipt.json"],
    },
}


def _canonical_sha256(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class ColabJobRequest:
    """Declarative request for a budget-capped Colab Pro+ parallel job."""

    job_id: str
    profile: str
    accelerator: str = "L4"
    num_workers: int = 1
    estimated_hours: float = 2.0
    compute_unit_cap: float = 100.0
    data_gate_passed: bool = False
    target_trajectories: int = STAGE1_MIN_PHYSAI_TRAJECTORIES
    dataset_refs: tuple[str, ...] = ()
    output_uri: str = "drive://flywheel/stage1"


def _build_notebook_cells(req: ColabJobRequest, profile_cfg: dict[str, Any], shard_id: int) -> list[dict[str, Any]]:
    cmd = str(profile_cfg["entrypoint"]).format(
        shard=shard_id,
        total=req.num_workers,
        input_dir="inputs/batch",
        out_dir=f"outputs/{req.job_id}/shard_{shard_id}",
        trajectories=max(1, req.target_trajectories // max(1, req.num_workers)),
        accelerator=req.accelerator,
        manifest="manifests/stage2_verified.json",
    )
    return [
        {
            "cell_type": "markdown",
            "source": [f"# {req.job_id} ({req.profile}, shard {shard_id}/{req.num_workers}, {req.accelerator})"],
        },
        {
            "cell_type": "code",
            "source": [
                "import json, pathlib",
                f"JOB_META = {json.dumps({'job_id': req.job_id, 'profile': req.profile, 'shard': shard_id, 'cap_cu': req.compute_unit_cap})}",
                "print('starting', JOB_META)",
            ],
        },
        {"cell_type": "code", "source": [f"!{cmd}"]},
    ]


def _refusal(req: ColabJobRequest, verdict: str, reason: str, est_cu: float) -> dict[str, Any]:
    body = {
        "schema": COLAB_JOB_SCHEMA,
        "ok": False,
        "verdict": verdict,
        "job_id": req.job_id,
        "profile": req.profile,
        "accelerator": req.accelerator,
        "estimated_compute_units": est_cu,
        "compute_unit_cap": req.compute_unit_cap,
        "data_gate_passed": req.data_gate_passed,
        "reason": reason,
        "shards": [],
        "next_valid_actions": ["colab.emit_stage1_job_spec", "flywheel.verify_three_plate"],
    }
    body["spec_sha256"] = _canonical_sha256(body)
    return body


def _validate_request(req: ColabJobRequest) -> tuple[dict[str, Any] | None, float, dict[str, Any] | None]:
    if req.profile not in COLAB_PROFILES:
        return None, 0.0, _refusal(req, "UNKNOWN_PROFILE", f"unsupported Colab profile: {req.profile}", 0.0)
    if req.accelerator not in ACCELERATOR_RATES:
        return None, 0.0, _refusal(req, "UNKNOWN_ACCELERATOR", f"unsupported accelerator: {req.accelerator}", 0.0)
    if req.num_workers < 1 or req.estimated_hours <= 0 or req.compute_unit_cap <= 0:
        return None, 0.0, _refusal(req, "INVALID_BUDGET", "workers, estimated_hours, and compute_unit_cap must be positive", 0.0)
    profile_cfg = COLAB_PROFILES[req.profile]
    est_cu = round(ACCELERATOR_RATES[req.accelerator] * req.num_workers * req.estimated_hours, 3)
    if profile_cfg["requires_data_gate"] and not req.data_gate_passed:
        return None, est_cu, _refusal(
            req, "NO_GO_DATA_GATE", "frontier pretraining refused: Stage-1/Stage-2 data sufficiency gate has not passed", est_cu,
        )
    if est_cu > req.compute_unit_cap:
        return None, est_cu, _refusal(
            req, "BUDGET_EXCEEDED", f"estimated compute units ({est_cu}) exceed cap ({req.compute_unit_cap})", est_cu,
        )
    if req.profile == "physai_trajectories" and req.target_trajectories < STAGE1_MIN_PHYSAI_TRAJECTORIES:
        return None, est_cu, _refusal(
            req, "BELOW_TRAJECTORY_FLOOR", f"physai_trajectories requires >= {STAGE1_MIN_PHYSAI_TRAJECTORIES} rollouts", est_cu,
        )
    return profile_cfg, est_cu, None


def emit_colab_job_spec(req: ColabJobRequest) -> dict[str, Any]:
    """Emit a deterministic colab-job/1 spec enforcing data-gate and compute-unit caps."""
    profile_cfg, est_cu, refusal = _validate_request(req)
    if refusal is not None or profile_cfg is None:
        return refusal if refusal is not None else _refusal(req, "INVALID", "validation failed", est_cu)
    shards = [
        {
            "shard_id": idx,
            "accelerator": req.accelerator,
            "notebook_cells": _build_notebook_cells(req, profile_cfg, idx),
            "expected_outputs": list(profile_cfg["outputs"]),
        }
        for idx in range(req.num_workers)
    ]
    body: dict[str, Any] = {
        "schema": COLAB_JOB_SCHEMA, "ok": True, "verdict": "READY",
        "job_id": req.job_id, "profile": req.profile, "stage": profile_cfg["stage"],
        "accelerator": req.accelerator, "num_workers": req.num_workers,
        "estimated_hours": req.estimated_hours, "estimated_compute_units": est_cu,
        "compute_unit_cap": req.compute_unit_cap, "data_gate_passed": req.data_gate_passed,
        "target_trajectories": req.target_trajectories if req.profile == "physai_trajectories" else None,
        "dataset_refs": list(req.dataset_refs), "output_uri": req.output_uri,
        "shards": shards, "next_valid_actions": ["flywheel.verify_three_plate"],
    }
    body["spec_sha256"] = _canonical_sha256(body)
    return body

"""Training report helpers for the optional encoder classifier."""
from __future__ import annotations

from typing import Any

from harness.evidence_json import canonical_sha256


def model_state_sha256(model: Any) -> str:
    from safetensors.torch import save

    tensors = {k: v.detach().cpu().contiguous() for k, v in model.state_dict().items()}
    return __import__("hashlib").sha256(save(tensors)).hexdigest()


def _manifest_basis(rows: list[dict]) -> list[dict]:
    return [{
        "example_sha256": row["example_sha256"],
        "task_family": row["task_family"],
        "source_group": row["source_group"],
    } for row in rows]


def build_training_report(
    *,
    rows: list[dict],
    config: Any,
    families: list[str],
    steps: int,
    examples_processed: int,
    losses: list[float],
    model: Any,
) -> dict:
    weights_sha = model_state_sha256(model)
    return {
        "schema": "flywheel.classifier-encoder-training-report/v1",
        "training_manifest_sha256": canonical_sha256(_manifest_basis(rows)),
        "artifact_identity": f"classifier-encoder:{weights_sha[:16]}",
        "weights_sha256": weights_sha,
        "seed": config.seed,
        "epochs": config.epochs,
        "learning_rate": float(config.learning_rate),
        "head_learning_rate": float(config.head_learning_rate),
        "accumulation_batch_size": config.batch_size,
        "max_steps": config.max_steps,
        "max_length": config.max_length,
        "fine_tune_last_n_layers": config.fine_tune_last_n_layers,
        "families": families,
        "counts": {
            "total_examples": len(rows),
            "explicit_abstain_examples": sum(not row["acceptable_choice_ids"] for row in rows),
            "optimization_steps": steps,
            "examples_processed": examples_processed,
        },
        "loss": {
            "first": losses[0] if losses else None,
            "mean": sum(losses) / len(losses) if losses else None,
            "last": losses[-1] if losses else None,
        },
        "calibration": {"status": "uncalibrated", "probability_semantics": "raw_softmax_like"},
        "does_not_prove": [
            "label truth, held-out generalization, calibration, or routing safety",
            "authorization, execution correctness, or verifier acceptance",
        ],
    }

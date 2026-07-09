# Flywheel-Local-Coder-32B Release Checklist

Status: blocked. Track status NO_TRAINED_ARTIFACT.

Gate ids match `scripts/run_model_publish_plan.py` and `scripts/run_model_release_readiness.py`.

| Gate id | Status | Evidence |
| --- | --- | --- |
| `trained_artifact_present` | FAILED | No trained 32B artifact exists. Only a checkpoint-2 training smoke (Phase-2 QLoRA hit the 24GB VRAM wall). Base weights must not be republished under a Flywheel name. |
| `root_exists` | DONE | `E:\local-model-run` exists; base weights at `E:\local-model-run\models\Qwen2.5-Coder-32B-Instruct`. |
| `weights_present` | blocked | Only base weights exist. A Flywheel release requires a trained artifact, not the base weights. |
| `endpoint_profiles_present` | pending | Blocked behind a trained artifact. |
| `endpoint_generation_ok` | pending | Blocked behind a trained artifact. |
| `benchmark_evidence_present` | pending | Blocked behind a trained artifact. |
| `release_docs_complete` | pending | Docs state NO_TRAINED_ARTIFACT until training completes. |
| Operator upload approval | pending, NEVER auto-approved | Not applicable until all prior gates pass. |

Verdict: do not publish. Unblock path: train a 32B adapter, build the provenance chain, re-enter the release pipeline.

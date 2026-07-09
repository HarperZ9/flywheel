# Flywheel-Local-Coder-14B Release Checklist

Status: blocked. The trained artifact exists; endpoint gate history and benchmark evidence do not.

Gate ids match `scripts/run_model_publish_plan.py` and `scripts/run_model_release_readiness.py`.

| Gate id | Status | Evidence |
| --- | --- | --- |
| `trained_artifact_present` | DONE | `E:\local-model-run\release\flywheel-local-coder-14b\telos-coder-14b-cpt2020-q4_k_m.gguf`, sha256 `613db240e3efc6730f24042a4602d1f12f1c6b397af1d5a4d74f4e064d4064be`. |
| `root_exists` | DONE | `E:\local-model-run` and the release directory exist. |
| `weights_present` | DONE | GGUF weight file present at the artifact path above (8,988,110,880 bytes). |
| `endpoint_profiles_present` | pending | `harness.model-endpoint-profiles/v1` artifact attached to the release row (backend ollama, model `flywheel-local-coder-14b`, `http://127.0.0.1:11434`). |
| `endpoint_generation_ok` | pending | `harness.model-endpoint-gate/v1` artifact with generation_ok for this model. |
| `benchmark_evidence_present` | pending | Executed benchmark artifacts attached to the release row. None exist yet. |
| `release_docs_complete` | pending | All required release docs present and scored 1.0 by the readiness run. |
| Operator upload approval | pending, NEVER auto-approved | Explicit operator approval after all gates pass. |

Verdict: do not publish.

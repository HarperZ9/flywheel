# Flywheel-Local-Coder-32B Release Checklist

Status: trained artifact present and verified. Endpoint gate history and benchmark evidence do not exist yet; the release ships with an explicit "no uplift claimed / benchmarks pending" null, matching the 14B track.

Gate ids match `scripts/run_model_publish_plan.py` and `scripts/run_model_release_readiness.py`.

| Gate id | Status | Evidence |
| --- | --- | --- |
| `trained_artifact_present` | DONE | `telos-coder-32b-cpt2019-q4_k_m.gguf`, sha256 `65e6133fbe4d12579a776047a71bebb98ab86f9e3d343ed821b51dac0ce312f4` (re-verified by re-hash). The hash, not a path, is the identity. |
| `root_exists` | DONE | The run root and its release directory exist on the build machine. |
| `weights_present` | DONE | GGUF weight file present at the artifact path above (19,851,336,480 bytes); merged fp16 also present. |
| `endpoint_profiles_present` | pending | `harness.model-endpoint-profiles/v1` artifact (backend ollama, model `flywheel-local-coder-32b`, `http://127.0.0.1:11434`). |
| `endpoint_generation_ok` | pending | `harness.model-endpoint-gate/v1` artifact with generation_ok for this model. A deterministic smoke MATCH is recorded; a formal gate artifact is not. |
| `benchmark_evidence_present` | pending | Executed benchmark artifacts attached to the release row. None exist yet. No uplift is claimed. |
| `release_docs_complete` | DONE | All required release docs present and refreshed to the verified artifact. |
| Operator upload approval | DONE | Approved (benchmarks-pending null kept); public at https://huggingface.co/zaindanaharper/flywheel-local-coder-32b since 2026-07-18. |

Verdict: releasable as a trained CPT derivative with a re-checkable provenance chain and an honest benchmark null. Upload is a deliberate operator action.

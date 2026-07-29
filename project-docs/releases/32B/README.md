---
license: apache-2.0
base_model: Qwen/Qwen2.5-Coder-32B-Instruct
tags:
  - code
  - gguf
  - qlora
  - local-first
  - verified-inference
pipeline_tag: text-generation
library_name: gguf
---

# Flywheel-Local-Coder-32B Release README

Status: staged, awaiting operator upload approval. The trained artifact and its full provenance chain exist and are re-checkable; benchmark evidence is pending.

## What this release is

`Flywheel-Local-Coder-32B` is the release name for a trained 32B artifact:

- Artifact file: `telos-coder-32b-cpt2019-q4_k_m.gguf` (Q4_K_M GGUF, 19,851,336,480 bytes).
- SHA-256: `65e6133fbe4d12579a776047a71bebb98ab86f9e3d343ed821b51dac0ce312f4`
- Identity: base `Qwen2.5-Coder-32B-Instruct` merged with QLoRA continued-pretraining adapter `checkpoint-2019` (2019 steps, epoch 0.25, r 16, alpha 32), then quantized to Q4_K_M.
- Also released: the QLoRA adapter `telos-coder-32b-cpt2019-lora.gguf` (LoRA GGUF, SHA-256 `08e7d21cfde1af768c877ecc18ee6343c87711c0c38b8c5b16feb9890f94cbac`) for applying the trained delta to the base or requantizing from it. The base weights themselves are never republished.
- Local serving: Ollama model name `flywheel-local-coder-32b`, created from the Modelfile beside the artifact.

## What evidence exists

- Provenance chain, recorded in `tasks/research/gguf_ship_manifest_checkpoint2019_32b.json`, each layer re-derivable:
  - corpus_content_hash `68345cdc6667f20d1678ac0a9139edc170348dfdebb9ae6045cde3d204f4fe62` (17,997 corpus files, shared pack with the 14B track)
  - pack_shards_hash `018798dfce7d4c86f5a6ea502a383553220f2e76facfe76acbe52b1c278ae543`
  - checkpoint_adapter_sha256 `d2ff1d3042c9b015d8d01b6e195cf95acedc133bf4efe78692e4349a3608e286`
  - LoRA GGUF sha256 `08e7d21cfde1af768c877ecc18ee6343c87711c0c38b8c5b16feb9890f94cbac`
  - GGUF (Q4_K_M) sha256 `65e6133fbe4d12579a776047a71bebb98ab86f9e3d343ed821b51dac0ce312f4`
- Deterministic smoke: ollama `/api/generate`, temp 0, seed 7, num_predict 64, byte-identical reruns (MATCH). Output hash prefix `403b2e8b21df9f55`.

## What is still missing

- Benchmark evidence. No benchmark has been run against this artifact. All benchmark claims are pending. No capability uplift over the base model is claimed.
- Endpoint gate history (`harness.model-endpoint-gate/v1` artifacts attached to the release row).
- Explicit operator approval for upload. Never auto-approved.

## Publication rule

The base `Qwen2.5-Coder-32B-Instruct` weights are never republished on their own; only the adapter and the merged quantization are released, with attribution. Any capability comparison against the base must come from executed benchmark artifacts, which do not exist yet.

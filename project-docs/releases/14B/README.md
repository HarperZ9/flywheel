---
license: apache-2.0
base_model: Qwen/Qwen2.5-Coder-14B-Instruct
tags:
  - code
  - gguf
  - qlora
  - local-first
  - verified-inference
pipeline_tag: text-generation
library_name: gguf
---

# Flywheel-Local-Coder-14B Release README

Status: staged, awaiting operator upload approval. Trained artifact, endpoint gate evidence, and first benchmark evidence exist.

## What this release is

`Flywheel-Local-Coder-14B` is the release name for a trained 14B artifact:

- Artifact file: `telos-coder-14b-cpt2020-q4_k_m.gguf` (Q4_K_M GGUF, 8,988,110,880 bytes).
- SHA-256: `613db240e3efc6730f24042a4602d1f12f1c6b397af1d5a4d74f4e064d4064be`
- Identity: base `Qwen2.5-Coder-14B-Instruct` merged with QLoRA continued-pretraining adapter `checkpoint-2020` (train_loss 0.035), then quantized to Q4_K_M.
- Artifact location: `E:\local-model-run\release\flywheel-local-coder-14b\telos-coder-14b-cpt2020-q4_k_m.gguf`
- Local serving: Ollama model name `flywheel-local-coder-14b`, created from the Modelfile in the same directory.

## What evidence exists

- Provenance chain, recorded in `C:\dev\local-model\tasks\research\gguf_ship_manifest_checkpoint2020.json`, each layer re-derivable:
  - corpus_content_hash `68345cdc6667f20d1678ac0a9139edc170348dfdebb9ae6045cde3d204f4fe62` (17,997 corpus files)
  - pack_shards_hash `018798dfce7d4c86f5a6ea502a383553220f2e76facfe76acbe52b1c278ae543`
  - checkpoint_adapter_sha256 `4de07c6ea342d1cc200d4a6e2b28a63f6ee37f34c5c0926c35d8c7db74d38d0f`
  - GGUF sha256 `613db240e3efc6730f24042a4602d1f12f1c6b397af1d5a4d74f4e064d4064be`
- Deterministic smoke: `llama-completion` at temp 0, seed 7, byte-identical reruns (MATCH). Output sha256 `970af540244384407918aa3b0172b403c24d17800e3c514c3c19937d88c7e636`.

## What is still missing

- Benchmark evidence. No benchmark has been run against this artifact. All benchmark claims are pending. No capability uplift over the base model is claimed.
- Endpoint gate history (`harness.model-endpoint-gate/v1` artifacts attached to the release row).
- Explicit operator approval for upload. Never auto-approved.

## Publication rule

This release stays blocked until every gate in `RELEASE-CHECKLIST.md` is satisfied by artifact paths, not narrative claims.

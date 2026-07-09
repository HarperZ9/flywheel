# Flywheel-Local-Coder-32B Release README

Status: NO_TRAINED_ARTIFACT. Publication blocked.

## What this track is

There is no trained 32B artifact. `Flywheel-Local-Coder-32B` is a track name only; no model exists under it.

## What exists

- Base weights `Qwen2.5-Coder-32B-Instruct` downloaded locally at `E:\local-model-run\models\Qwen2.5-Coder-32B-Instruct`.
- A checkpoint-2 training smoke only. Phase-2 QLoRA on the 32B hit the 24GB VRAM wall; no usable adapter was produced.

## Publication rule

The base Qwen2.5-Coder-32B-Instruct weights must NOT be republished under a Flywheel name. Any 32B publication is blocked until a real trained artifact exists.

## Path to unblock

1. Train a 32B adapter to completion (requires solving the VRAM constraint).
2. Build the full provenance chain (corpus -> shards -> checkpoint -> artifact), as done for the 14B track.
3. Re-enter the release pipeline and pass every gate in `RELEASE-CHECKLIST.md`.
